import copy
import importlib.util
import json
import sqlite3
import tempfile
import types
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from time import monotonic_ns
from unittest.mock import patch

from game_agent.config import Context, load_config
from game_agent.contracts import Action, Game, Plan, State, Step, matches
from game_agent.plugins.base import Plugin
from game_agent.plugins.demo import DemoCapture, DemoController, FactsPerception
from game_agent.plugins.memory import SQLiteMemory
from game_agent.plugins.policy import TemplatePolicy
from game_agent.registry import PluginSpec, registry_for
from game_agent.runtime import Application

ROOT = Path(__file__).resolve().parents[1]


class StaleCapture(DemoCapture):
    def capture(self):
        frame = super().capture()
        frame.captured_ns -= 10_000_000_000
        return frame


class DuplicateCapture(DemoCapture):
    def capture(self):
        frame = super().capture()
        frame.sequence = 1
        return frame


class FailedController(DemoController):
    def execute(self, action, state):
        raise RuntimeError("device disconnected")

    def release_all(self):
        self.context.services["released"] = True


class SpyController(DemoController):
    def execute(self, action, state):
        self.context.services["sent"] = True
        return super().execute(action, state)

    def release_all(self):
        self.context.services["released"] = True


class LiveCapture(DemoCapture):
    mode = "live"

    def capture(self):
        frame = super().capture()
        frame.focused = False
        return frame


class LiveController(SpyController):
    mode = "live"


class RecordedCapture(DemoCapture):
    mode = "replay"

    def capture(self):
        frame = super().capture()
        frame.facts.update(shop_open=True, has_sword=True, equipped=True)
        return frame


class SlowPolicy(TemplatePolicy):
    def choose(self, step, state):
        self.context.services["policy_called"] = True
        from time import sleep
        sleep(0.015)
        return super().choose(step, state)


class ClosedCapture(DemoCapture):
    def close(self):
        self.context.services["capture_closed"] = True


class BrokenPerception(FactsPerception):
    def __init__(self, context, options):
        raise ValueError("model initialization failed")


class MemoryAndExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = load_config(ROOT / "configs/demo.toml").config
        self.config["runtime"].update(tick_hz=120, max_ticks=15)
        self.plan = Plan.from_dict(json.loads((ROOT / "examples/shop-tutorial.json").read_text(encoding="utf-8")))

    def context(self):
        return Context(self.root, copy.deepcopy(self.config))

    def registry(self, context, **overrides):
        registry = registry_for(context)
        for role, cls in overrides.items():
            name = "test." + role
            registry.add(PluginSpec(name, role, "1.0.0", 1, __name__ + ":" + cls.__name__))
            context.config["plugins"][role] = {"use": name}
        return registry

    def test_execute_restart_recall_train_and_replace_policy(self):
        with Application(self.context()) as app:
            result = app.run(self.plan)
            self.assertEqual(result["status"], "success")
        # Fresh process-style context: persisted data, no surviving world/policy state.
        with Application(self.context()) as app:
            memory = app.plugin("memory")
            self.assertEqual(memory.recall("购买", self.plan.game, "simulation")[0]["successes"], 1)
            self.assertEqual(memory.load_plan(self.plan.id, self.plan.game), self.plan)
            samples = memory.examples(self.plan.game, "simulation")
            self.assertEqual([s["action"]["key"] for s in samples], ["B", "1", "E"])
            learned = app.plugin("learner").train(samples, "memory/model.json")
            self.assertEqual(learned["states"], 3)
        context = self.context()
        context.config["plugins"]["policy"] = {"use": "experience.policy", "options": {"model": "memory/model.json"}}
        with Application(context) as app:
            self.assertEqual(app.run(self.plan)["status"], "success")

    def test_dry_run_never_changes_game_or_teaches_actions(self):
        context = self.context()
        context.config["plugins"]["controller"] = {"use": "dry-run.controller"}
        with Application(context) as app:
            result = app.run(self.plan)
            self.assertNotEqual(result["status"], "success")
            self.assertFalse(context.services["demo.world"].equipped)
            memory = app.plugin("memory")
            self.assertEqual(memory.examples(self.plan.game, "simulation"), [])
            self.assertEqual(memory.recall("", self.plan.game, "simulation")[0]["status"], "candidate")

    def test_replay_observed_success_is_not_live_skill(self):
        context = self.context()
        context.config["runtime"]["mode"] = "replay"
        context.config["plugins"]["controller"] = {"use": "dry-run.controller"}
        with Application(context, self.registry(context, capture=RecordedCapture)) as app:
            self.assertEqual(app.run(self.plan)["status"], "dry-run")
            memory = app.plugin("memory")
            self.assertEqual(memory.examples(self.plan.game, "live"), [])
            self.assertEqual(memory.recall("", self.plan.game, "live")[0]["successes"], 0)

    def test_device_failure_is_recorded_and_keys_are_released(self):
        context = self.context()
        with Application(context, self.registry(context, controller=FailedController)) as app:
            result = app.run(self.plan)
            self.assertEqual(result["status"], "error")
            self.assertIn("device disconnected", result["reason"])
            self.assertTrue(context.services["released"])
            path = self.root / "run.jsonl"
            app.plugin("memory").export_run(result["run_id"], path)
            rows = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["run"]["status"], "error")

    def test_stale_frame_cannot_send_input(self):
        context = self.context()
        registry = self.registry(context, capture=StaleCapture, controller=SpyController)
        with Application(context, registry) as app:
            result = app.run(self.plan)
            self.assertIn("stale", result["reason"])
            self.assertNotIn("sent", context.services)
            self.assertTrue(context.services["released"])

    def test_slow_policy_cannot_send_action_for_expired_frame(self):
        context = self.context()
        context.config["runtime"]["max_frame_age_ms"] = 5
        registry = self.registry(context, policy=SlowPolicy, controller=SpyController)
        with Application(context, registry) as app:
            result = app.run(self.plan)
            self.assertIn("stale", result["reason"])
            self.assertNotIn("sent", context.services)

    def test_focus_loss_blocks_live_action(self):
        context = self.context()
        context.config["runtime"]["mode"] = "live"
        registry = self.registry(context, capture=LiveCapture, controller=LiveController)
        with Application(context, registry) as app:
            result = app.run(self.plan, live=True)
            self.assertIn("focused", result["reason"])
            self.assertNotIn("sent", context.services)

    def test_stop_file_prevents_actions(self):
        context = self.context()
        (self.root / "memory").mkdir()
        (self.root / "memory/STOP").touch()
        with Application(context, self.registry(context, controller=SpyController)) as app:
            self.assertIn("stop file", app.run(self.plan)["reason"])
            self.assertNotIn("sent", context.services)

    def test_explicit_live_required_before_plugins_start(self):
        context = self.context()
        context.config["runtime"]["mode"] = "live"
        with Application(context) as app:
            with self.assertRaisesRegex(ValueError, "--live"):
                app.run(self.plan)
            self.assertEqual(app.instances, {})

    def test_plugin_initialization_failure_closes_prior_plugins(self):
        context = self.context()
        registry = self.registry(context, capture=ClosedCapture, perception=BrokenPerception)
        with self.assertRaisesRegex(ValueError, "initialization failed"):
            with Application(context, registry) as app:
                app.run(self.plan)
        self.assertTrue(context.services["capture_closed"])

    def test_profile_and_mode_isolation(self):
        context = self.context()
        with Application(context) as app:
            app.run(self.plan)
            memory = app.plugin("memory")
            other = replace(self.plan.game, profile="other-layout")
            self.assertEqual(memory.recall("", other, "simulation"), [])
            with self.assertRaises(ValueError):
                memory.load_plan(self.plan.id, other)
            self.assertEqual(memory.examples(self.plan.game, "live"), [])

    def test_interrupted_run_does_not_become_training_data(self):
        with Application(self.context()) as app:
            memory = app.plugin("memory")
            run_id = memory.begin(self.plan, "simulation", {})
            memory.append(run_id, "step_verified", {"applied": True})
        with Application(self.context()) as app:
            self.assertEqual(app.plugin("memory").examples(self.plan.game, "simulation"), [])

    def test_ingest_is_content_addressed(self):
        context = self.context()
        path = self.root / "tutorial.json"
        path.write_text(json.dumps(asdict(self.plan)))
        with Application(context) as app:
            first = app.ingest("tutorial.json")
            self.assertEqual(first, app.ingest("tutorial.json"))
            path.write_text(json.dumps(asdict(replace(self.plan, title="新教程"))))
            self.assertNotEqual(first, app.ingest("tutorial.json"))

    def test_future_memory_schema_is_not_overwritten(self):
        path = self.root / "future.db"
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA user_version=42")
        with self.assertRaisesRegex(ValueError, "migration required"):
            SQLiteMemory(self.context(), {"path": "future.db"})
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 42)

    def test_unknown_state_is_not_false(self):
        self.assertFalse(matches({}, {"equipped": False}))
        self.assertFalse(matches({"count": True}, {"count": 1}))

    def test_repeated_frame_cannot_verify_action(self):
        context = self.context()
        with Application(context, self.registry(context, capture=DuplicateCapture)) as app:
            result = app.run(self.plan)
            self.assertIn("new frame", result["reason"])
            self.assertEqual(app.plugin("memory").examples(self.plan.game, "simulation"), [])

    def test_conflicting_experience_is_not_silently_used(self):
        context = self.context()
        with Application(context) as app:
            app.run(self.plan)
            samples = app.plugin("memory").examples(self.plan.game, "simulation")
            conflict = copy.deepcopy(samples[0])
            conflict["template"]["key"] = "E"
            app.plugin("learner").train(samples + [conflict], "memory/conflict.json")
        context = self.context()
        context.config["plugins"]["policy"] = {"use": "experience.policy", "options": {"model": "memory/conflict.json"}}
        with Application(context) as app:
            self.assertIn("disagree", app.run(self.plan)["reason"])

    def test_target_click_tracks_current_geometry(self):
        step = Step("click", "buy", {}, {"done": True}, {"kind": "click", "target": "sword"})
        policy = TemplatePolicy(self.context(), {})
        state = State(1, monotonic_ns(), {}, {"sword": [[0.2, 0.3, 0.4, 0.5]]})
        action = policy.choose(step, state)
        self.assertAlmostEqual(action.x, 0.3)
        self.assertEqual(action.template(), {"kind": "click", "target": "sword", "duration_ms": 50})
        state = replace(state, targets={"sword": [[0.2, 0.3, 0.4, 0.5], [0.5, 0.5, 0.6, 0.6]]})
        with self.assertRaisesRegex(ValueError, "exactly one"):
            policy.choose(step, state)


class ConfigurationTests(unittest.TestCase):
    def test_override_replaces_only_selected_plugin(self):
        base = load_config(ROOT / "configs/demo.toml")
        derived = load_config(ROOT / "configs/learned-demo.toml")
        self.assertEqual(base.config["plugins"]["capture"], derived.config["plugins"]["capture"])
        self.assertEqual(derived.config["plugins"]["policy"]["use"], "experience.policy")

    def test_wrong_plugin_api_is_rejected(self):
        registry = registry_for(load_config(ROOT / "configs/demo.toml"))
        with self.assertRaisesRegex(ValueError, "incompatible"):
            registry.add(PluginSpec("bad", "policy", "1", 99, "bad:Policy"))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            registry.add(registry.specs["template.policy"])

    def test_wrong_plugin_role_is_rejected(self):
        context = load_config(ROOT / "configs/demo.toml")
        registry = registry_for(context)
        context.config["plugins"]["policy"] = {"use": "demo.controller"}
        with self.assertRaisesRegex(ValueError, "does not provide"):
            registry.create("policy", context)

    def test_external_manifest_loads_without_core_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plugin.toml"
            path.write_text(f'''[[plugins]]
id="custom.policy"
role="policy"
version="1.0.0"
api_version=1
factory="{__name__}:SlowPolicy"
''')
            context = load_config(ROOT / "configs/demo.toml")
            context.config["plugin_manifests"] = [str(path)]
            context.config["plugins"]["policy"] = {"use": "custom.policy"}
            self.assertIsInstance(registry_for(context).create("policy", context), SlowPolicy)

    def test_lazy_loading_does_not_import_gpu_for_demo(self):
        context = load_config(ROOT / "configs/demo.toml")
        real_import = __import__

        def limited(name, *a, **kw):
            if name.split(".")[0] in {"torch", "ultralytics", "cv2", "transformers"}:
                raise AssertionError(f"unexpected import: {name}")
            return real_import(name, *a, **kw)

        with patch("builtins.__import__", side_effect=limited):
            registry_for(context).create("policy", context)

    def test_paths_cannot_escape_project_and_urls_are_not_read(self):
        context = load_config(ROOT / "configs/demo.toml")
        with self.assertRaises(ValueError):
            context.output_path("../escape.json")
        with self.assertRaises(ValueError):
            context.input_path("https://example.org/video.mp4")

    def test_invalid_action_is_rejected(self):
        for kwargs in ({"kind": "shell"}, {"kind": "click", "x": float("nan"), "y": 0.5},
                       {"kind": "key", "key": "W", "duration_ms": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Action(**kwargs)

    def test_inheritance_cycles_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cycle.toml"
            path.write_text('extends="cycle.toml"')
            with self.assertRaisesRegex(ValueError, "cycle"):
                load_config(path)


class UInputBackendTests(unittest.TestCase):
    def test_actual_backend_releases_key_if_focus_changes(self):
        from game_agent.plugins.hyprland import UInputController
        ecodes = types.SimpleNamespace(EV_KEY=1, EV_REL=2, REL_X=0, REL_Y=1,
                                       BTN_LEFT=272, KEY_B=48, KEY_1=2, KEY_E=18)

        class Device:
            def __init__(self, *args, **kwargs):
                self.events = []
                self.closed = False
            def write(self, *event):
                self.events.append(event)
            def syn(self):
                pass
            def close(self):
                self.closed = True

        evdev = types.SimpleNamespace(UInput=Device, ecodes=ecodes)
        with tempfile.TemporaryDirectory() as folder, patch.dict("sys.modules", {"evdev": evdev}):
            context = load_config(ROOT / "configs/demo.toml")
            context.root = Path(folder)
            context.services["live_enabled"] = True
            controller = UInputController(context, {"window_class": "Game"})
            window = {"class": "Game", "address": "0xabc", "at": [10, 20], "size": [640, 360]}
            state = State(1, monotonic_ns(), {"__window_rect": [10, 20, 640, 360]},
                          focused=True, window_id="0xabc")
            try:
                with patch("game_agent.plugins.hyprland.active_window", side_effect=[window, {"class": "Editor"}]):
                    with self.assertRaisesRegex(ValueError, "not focused"):
                        controller.execute(Action("key", key="B", duration_ms=100), state)
                self.assertEqual(controller.device.events, [(1, 48, 1), (1, 48, 0)])
                self.assertEqual(controller.held, set())
            finally:
                controller.close()
            self.assertTrue(controller.device.closed)


@unittest.skipUnless(importlib.util.find_spec("cv2"), "optional OpenCV not installed")
class VideoTests(unittest.TestCase):
    def test_decode_a_real_local_video_and_capture_eof(self):
        import cv2
        import numpy as np
        from game_agent.media import sample_video
        from game_agent.plugins.video import VideoCapture
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "clip.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
            self.assertTrue(writer.isOpened())
            try:
                for i in range(10):
                    writer.write(np.full((48, 64, 3), i * 20, dtype=np.uint8))
            finally:
                writer.release()
            metadata, frames = sample_video(path, 4)
            self.assertEqual(metadata["frames"], 10)
            self.assertEqual(len(frames), 4)
            self.assertAlmostEqual(metadata["duration_s"], 1)
            context = load_config(ROOT / "configs/demo.toml")
            capture = VideoCapture(context, {"path": str(path)})
            try:
                self.assertTrue(all(capture.capture() is not None for _ in range(10)))
                self.assertIsNone(capture.capture())
            finally:
                capture.close()


if __name__ == "__main__":
    unittest.main()
