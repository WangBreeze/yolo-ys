import copy
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from game_agent.config import Context, load_config
from game_agent.media import file_sha256, sample_video
from game_agent.plugins.base import Plugin
from game_agent.plugins.download import YouGetDownloader
from game_agent.registry import PluginSpec, registry_for
from game_agent.runtime import Application
from game_agent.video_contracts import parse_description
from game_agent.video_library import VideoLibrary
from game_agent.video_workflow import cached_digest, understand

ROOT = Path(__file__).resolve().parents[1]


class FakeSemantic(Plugin):
    ROLE = "semantic"

    def identity(self):
        return {"version": self.options.get("revision", "1")}

    def describe(self, frames, transcript, max_tokens):
        self.context.services.setdefault("descriptions", []).append({"frames": frames, "transcript": transcript})
        return {"description": {"summary": "测试画面内容", "observations": ["看到画面"],
                                "operation_intents": [], "uncertainties": ["未知实际按键"]},
                "metrics": {"inference_s": 0.001}}


class FakeSpeech(Plugin):
    ROLE = "speech"

    def identity(self):
        return {"revision": self.options.get("revision", "1")}

    def transcribe(self, source):
        self.context.services["asr_calls"] = self.context.services.get("asr_calls", 0) + 1
        return {"status": "transcribed", "segments": [{"start_s": 0, "end_s": 1, "text": "打开商店"}]}


@unittest.skipUnless(importlib.util.find_spec("cv2") and shutil.which("ffprobe"), "optional video dependencies")
class VideoWorkflowTests(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy as np
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = copy.deepcopy(load_config(ROOT / "configs/video.toml").config)
        self.context = Context(self.root, config)
        self.video = self.root / "tutorial.avi"
        writer = cv2.VideoWriter(str(self.video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 180))
        self.assertTrue(writer.isOpened())
        for i in range(20):
            frame = np.zeros((180, 320, 3), dtype=np.uint8)
            frame[:, :, i // 10] = 180
            writer.write(frame)
        writer.release()
        self.registry = registry_for(self.context)
        for role, cls in (("semantic", FakeSemantic), ("speech", FakeSpeech)):
            plugin_id = "fake." + role
            self.registry.add(PluginSpec(plugin_id, role, "1.0.0", 1, __name__ + ":" + cls.__name__))
            self.context.config["plugins"][role] = {"use": plugin_id}

    def test_classification_preserves_original_and_survives_restart(self):
        original = file_sha256(self.video)
        with VideoLibrary(self.context) as library:
            row = library.add(str(self.video))
            self.assertEqual(row["category"], "tutorial")
            library.classify(row["id"], "gameplay")
            self.assertEqual(library.add(str(self.video))["category"], "gameplay")
        with VideoLibrary(self.context) as library:
            self.assertEqual(library.get(row["id"])["category_label"], "游戏实录")
            stored = self.root / row["media"][0]["path"]
            self.assertEqual(file_sha256(stored), original)
            self.assertEqual(file_sha256(self.video), original)

    def test_default_download_only_acquires_and_classifies(self):
        class Downloader:
            def download(inner, url, destination):
                shutil.copyfile(self.video, destination / "raw.avi")
        with VideoLibrary(self.context) as library:
            row = library.add("https://example.com/tutorial", Downloader())
            self.assertEqual(row["classification_source"], "default")
            self.assertFalse((library.root / "reports").exists())
            self.assertEqual(file_sha256(self.root / row["media"][0]["path"]), file_sha256(self.video))

    def test_download_failure_not_cataloged(self):
        class Broken:
            def download(self, url, destination):
                (destination / "clip.part").write_text("partial")
                raise RuntimeError("download failed")
        with VideoLibrary(self.context) as library:
            with self.assertRaises(RuntimeError):
                library.add("https://example.com/failure", Broken())
            self.assertEqual(library.list(), [])

    def test_semantic_report_cached_without_loading_controller_or_resampling(self):
        with Application(self.context, self.registry) as app, VideoLibrary(self.context) as library:
            first = understand(app, library, str(self.video))
            self.assertFalse(first["cache_hit"])
            self.assertEqual(first["audio"]["status"], "absent")
            self.assertEqual(len(first["metadata"]["sampled_seconds"]), 12)
            self.assertEqual(set(app.instances), {"semantic"})
            with patch("game_agent.video_workflow.sample_video", side_effect=AssertionError("cache decoded again")):
                second = understand(app, library, str(self.video))
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["timings"], second["timings"])
            self.assertTrue(Path(second["report_markdown"]).is_file())
            self.assertEqual(second["status"], "candidate_understanding")
            self.assertNotIn("steps", second)

    def test_preset_and_model_revision_invalidate_cache(self):
        with Application(self.context, self.registry) as app, VideoLibrary(self.context) as library:
            first = understand(app, library, str(self.video))
            second = understand(app, library, str(self.video), "balanced")
            self.assertFalse(second["cache_hit"])
            self.assertNotEqual(first["cache_key"], second["cache_key"])
            app.plugin("semantic").options["revision"] = "2"
            third = understand(app, library, str(self.video))
            self.assertNotEqual(first["cache_key"], third["cache_key"])

    def test_content_changed_with_same_size_and_mtime_invalidates_digest(self):
        path = self.root / "content.txt"
        path.write_text("first")
        original = path.stat()
        before = cached_digest(path, self.root / "cache")
        path.write_text("other")
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assertNotEqual(before, cached_digest(path, self.root / "cache"))

    def test_windows_digest_does_not_trust_creation_time_as_change_time(self):
        path = self.root / "content.txt"
        path.write_text("first")
        cache = self.root / "cache"
        with patch("game_agent.video_workflow._METADATA_DIGEST_CACHE_SAFE", False), \
                patch("game_agent.video_workflow.file_sha256", wraps=file_sha256) as digest:
            cached_digest(path, cache)
            cached_digest(path, cache)
        self.assertEqual(digest.call_count, 2)

    def test_timed_transcript_included_only_in_matching_segment(self):
        transcript = self.root / "transcript.json"
        transcript.write_text(json.dumps([{"start_s": 0.0, "end_s": 0.2, "text": "打开商店"}]))
        with Application(self.context, self.registry) as app, VideoLibrary(self.context) as library:
            result = understand(app, library, str(self.video), preset="balanced", transcript=str(transcript))
            calls = self.context.services["descriptions"]
            self.assertIn("打开商店", calls[0]["transcript"])
            self.assertEqual(calls[1]["transcript"], "")
            self.assertEqual(result["audio"]["status"], "provided")
            self.assertNotIn("speech", app.instances)

    def test_speech_cache_reused_across_visual_presets(self):
        from game_agent.video_library import probe
        info = {**probe(self.video), "audio": True}
        with Application(self.context, self.registry) as app, VideoLibrary(self.context) as library:
            with patch("game_agent.video_workflow.probe", return_value=info):
                first = understand(app, library, str(self.video))
                second = understand(app, library, str(self.video), "balanced")
            self.assertEqual(self.context.services["asr_calls"], 1)
            self.assertFalse(first["audio"]["cache_hit"])
            self.assertTrue(second["audio"]["cache_hit"])

    def test_sampler_bounds_size_and_does_not_write_frames(self):
        files = set(self.root.iterdir())
        meta, frames = sample_video(self.video, 4, max_edge=100, hash_content=False)
        self.assertEqual(len(frames), 4)
        self.assertIsNone(meta["sha256"])
        self.assertTrue(all(max(image.shape[:2]) <= 100 for _, image in frames))
        self.assertEqual(files, set(self.root.iterdir()))

    def test_failed_description_not_cached(self):
        with Application(self.context, self.registry) as app, VideoLibrary(self.context) as library:
            with patch.object(app.plugin("semantic"), "describe", return_value={"description": {"summary": "bad"}}):
                with self.assertRaises(ValueError):
                    understand(app, library, str(self.video))
            self.assertFalse((library.root / "reports").exists())

    def test_optimized_sampler_keeps_exact_frames_and_timestamps(self):
        import cv2
        import numpy as np
        _, frames = sample_video(self.video, 12, hash_content=False)
        reader = cv2.VideoCapture(str(self.video))
        try:
            for timestamp, image in frames:
                reader.set(cv2.CAP_PROP_POS_FRAMES, round(timestamp * 10))
                ok, direct = reader.read()
                self.assertTrue(ok)
                np.testing.assert_array_equal(image, direct)
        finally:
            reader.release()

    def test_future_catalog_schema_is_rejected_without_overwriting(self):
        folder = self.root / "memory/videos"
        folder.mkdir(parents=True)
        with closing(sqlite3.connect(folder / "catalog.sqlite3")) as db, db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaises(ValueError):
            VideoLibrary(self.context)
        with closing(sqlite3.connect(folder / "catalog.sqlite3")) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 99)

    def test_cache_survives_application_restart_and_keeps_original_compute_time(self):
        with Application(self.context, self.registry) as app, VideoLibrary(self.context) as library:
            original = understand(app, library, str(self.video))
        self.context.services.clear()
        with Application(self.context, self.registry) as app, VideoLibrary(self.context) as library:
            result = understand(app, library, str(self.video))
            self.assertTrue(result["cache_hit"])
            self.assertNotIn("descriptions", self.context.services)
            self.assertEqual(original["timings"], result["timings"])


class DownloadContractTests(unittest.TestCase):
    def test_shell_free_downloader_disables_merging_and_caption_download(self):
        context = load_config(ROOT / "configs/video.toml")
        plugin = YouGetDownloader(context, {})
        with patch("game_agent.plugins.download.importlib.util.find_spec", return_value=True):
            with patch("game_agent.plugins.download.subprocess.run") as run:
                plugin.download("https://example.com/watch?v=1&name=$(test)", Path("/tmp/output"))
                command = run.call_args.args[0]
                self.assertIn("--no-merge", command)
                self.assertIn("--no-caption", command)
                self.assertFalse(run.call_args.kwargs.get("shell", False))
                self.assertEqual(command[-1], "https://example.com/watch?v=1&name=$(test)")

    def test_model_payload_must_have_explicit_uncertainty_and_intent_fields(self):
        with self.assertRaises(ValueError):
            parse_description('{"summary":"pretend plan", "steps":[]}')
