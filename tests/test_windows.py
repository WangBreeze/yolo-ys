import copy
import ctypes
import importlib.util
import tempfile
import unittest
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from time import monotonic_ns
from unittest.mock import patch

from game_agent.config import load_config
from game_agent.contracts import Action, State
from game_agent.plugins.windows import (Input, Win32Desktop, WindowsCapture, WindowsController,
                                        absolute_position, check_window, virtual_key)

ROOT = Path(__file__).resolve().parents[1]


class FakeDesktop:
    def __init__(self):
        self.window = {"id": "abcd:42", "class": "Game", "title": "原神",
                       "visible": True, "minimized": False, "rect": [-800, 20, 640, 360]}
        self.events = []
        self.down = set()
        self.after_press = None

    def foreground(self):
        return copy.deepcopy(self.window)

    def dpi(self):
        return nullcontext()

    def is_down(self, key):
        return key in self.down

    def key(self, key, down):
        self.events.append(("key", key, down))
        if down and self.after_press:
            self.after_press()

    def button(self, down):
        self.events.append(("button", down))

    def move(self, x, y, absolute=False):
        self.events.append(("move", x, y, absolute))


class WindowsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.context = load_config(ROOT / "configs/demo.toml")
        self.context.root = Path(temp.name)
        self.context.config["runtime"].update(mode="live", max_frame_age_ms=1000)
        self.context.services["live_enabled"] = True
        self.desktop = FakeDesktop()
        patcher = patch("game_agent.plugins.windows.Win32Desktop", return_value=self.desktop)
        patcher.start()
        self.addCleanup(patcher.stop)

    def controller(self):
        result = WindowsController(self.context, {"window_class": "Game", "window_title": "原神"})
        self.addCleanup(result.close)
        return result

    def state(self):
        return State(1, monotonic_ns(), {"__window_rect": list(self.desktop.window["rect"])},
                     focused=True, window_id="abcd:42")

    def test_input_layout_matches_windows_abi(self):
        self.assertEqual(ctypes.sizeof(Input), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        self.assertEqual(Input.value.offset, 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4)

    def test_non_windows_rejects_native_backend_before_loading_dll(self):
        with patch("game_agent.plugins.windows.sys.platform", "linux"):
            with self.assertRaisesRegex(RuntimeError, "Windows 10/11"):
                Win32Desktop()

    def test_input_requires_explicit_live_mode(self):
        self.context.services.clear()
        with self.assertRaisesRegex(ValueError, "--live"):
            WindowsController(self.context, {"window_class": "Game"})
        self.assertEqual(self.desktop.events, [])

    def test_focus_loss_releases_pressed_key(self):
        controller = self.controller()
        self.desktop.after_press = lambda: self.desktop.window.update(title="Editor")
        with self.assertRaisesRegex(ValueError, "foreground"):
            controller.execute(Action("key", key="B", duration_ms=30), self.state())
        self.assertEqual(self.desktop.events, [("key", 66, True), ("key", 66, False)])
        self.assertFalse(controller.held)

    def test_send_failure_still_attempts_release(self):
        controller = self.controller()
        def fail():
            raise OSError("failed key-down")
        self.desktop.after_press = fail
        with self.assertRaises(OSError):
            controller.execute(Action("key", key="B"), self.state())
        self.assertEqual(self.desktop.events[-1], ("key", 66, False))

    def test_geometry_identity_staleness_and_stop_block_input(self):
        controller = self.controller()
        for case in ("rect", "id", "stale", "unfocused", "stop", "f12"):
            with self.subTest(case=case):
                state = self.state()
                stop = self.context.output_path("memory/STOP")
                if case == "rect": state.facts["__window_rect"][0] += 1
                if case == "id": state = replace(state, window_id="another:process")
                if case == "stale": state = replace(state, captured_ns=state.captured_ns - 2_000_000_000)
                if case == "unfocused": state = replace(state, focused=False)
                if case == "stop":
                    stop.parent.mkdir(exist_ok=True)
                    stop.touch()
                if case == "f12": self.desktop.down.add(0x7B)
                with self.assertRaises(ValueError):
                    controller.execute(Action("key", key="B"), state)
                self.assertEqual(self.desktop.events, [])
                stop.unlink(missing_ok=True)
                self.desktop.down.clear()

    def test_user_held_key_is_not_pressed_or_released(self):
        controller = self.controller()
        self.desktop.down.add(66)
        with self.assertRaisesRegex(ValueError, "already held"):
            controller.execute(Action("key", key="B"), self.state())
        self.assertEqual(self.desktop.events, [])

    def test_click_resolves_client_coordinates_on_negative_origin_monitor(self):
        self.controller().execute(Action("click", x=1, y=0.5, duration_ms=0), self.state())
        self.assertEqual(self.desktop.events, [("move", -161, 200, True), ("button", True), ("button", False)])
        self.assertEqual(absolute_position(-1920, 0, [-1920, 0, 3840, 1080]), (0, 0))
        self.assertEqual(absolute_position(1919, 1079, [-1920, 0, 3840, 1080]), (65535, 65535))

    def test_window_must_be_visible_not_minimized_and_exactly_match(self):
        for changes in ({"minimized": True}, {"visible": False}, {"title": "原神2"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                check_window({**self.desktop.window, **changes}, {"window_title": "原神"})
        with self.assertRaises(ValueError): virtual_key("UNKNOWN")

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "optional numpy")
    def test_capture_preserves_bgr_and_rejects_geometry_change(self):
        import numpy as np
        class Grabber:
            closed = False
            def grab(inner, rect):
                pixels = np.full((360, 640, 4), (1, 2, 3, 255), dtype=np.uint8)
                if getattr(inner, "change", False): self.desktop.window["rect"][0] += 1
                return pixels
            def close(inner): inner.closed = True
        grabber = Grabber()
        with patch("game_agent.plugins.windows.create_grabber", return_value=grabber):
            capture = WindowsCapture(self.context, {"window_class": "Game"})
        try:
            frame = capture.capture()
            self.assertEqual(frame.pixels[0, 0].tolist(), [1, 2, 3])
            self.assertEqual(frame.facts["__window_rect"], [-800, 20, 640, 360])
            grabber.change = True
            with self.assertRaisesRegex(ValueError, "moved"):
                capture.capture()
        finally:
            capture.close()
        self.assertTrue(grabber.closed)
