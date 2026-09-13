import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from game_agent.cli import doctor
from game_agent.config import load_config
from game_agent.registry import registry_for
from game_agent.video_workflow import write_json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_project", ROOT / "tools/package-project.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class PortabilityTests(unittest.TestCase):
    def test_windows_config_is_recognized_but_not_claimed_ready_on_linux(self):
        context = load_config(ROOT / "configs/windows.example.toml")
        with patch("game_agent.cli.sys.platform", "linux"):
            report = doctor(context, registry_for(context))
        self.assertFalse(report["ok"])
        self.assertTrue(any("requires Windows" in issue for issue in report["issues"]))
        self.assertEqual(context.config["plugins"]["controller"]["use"], "dry-run.controller")

    def test_offline_config_does_not_select_live_input(self):
        context = load_config(ROOT / "configs/offline-training.toml")
        self.assertEqual(context.mode, "replay")
        self.assertEqual(context.config["plugins"]["controller"]["use"], "dry-run.controller")

    def test_atomic_json_failure_cleans_temporary_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "报告.json"
            write_json(path, {"text": "原始"})
            with patch("game_agent.video_workflow.os.replace", side_effect=OSError("test failure")):
                with self.assertRaises(OSError):
                    write_json(path, {"text": "新内容"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"text": "原始"})
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_bundle_preserves_committed_sqlite_wal_and_omits_machine_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "configs").mkdir()
            (root / "configs/demo.toml").write_text('title="中文"', encoding="utf-8")
            (root / "configs/private.local.toml").write_text("local settings", encoding="utf-8")
            memory = root / "memory"
            memory.mkdir()
            db = sqlite3.connect(memory / "catalog.sqlite3")
            self.addCleanup(db.close)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE sample (value TEXT)")
            db.execute("INSERT INTO sample VALUES ('视频教程')")
            db.commit()
            result = packager.package(root, memory / "windows.zip", ["memory/catalog.sqlite3"])
            with zipfile.ZipFile(result["path"]) as archive:
                self.assertNotIn("configs/private.local.toml", archive.namelist())
                manifest = json.loads(archive.read("TRANSFER-MANIFEST.json"))
                for name, digest in manifest["files"].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
                snapshot = root / "snapshot.sqlite3"
                snapshot.write_bytes(archive.read("memory/catalog.sqlite3"))
            with sqlite3.connect(snapshot) as copied:
                self.assertEqual(copied.execute("SELECT value FROM sample").fetchone()[0], "视频教程")
            copied.close()
            db.close()

    def test_bundle_rejects_windows_reserved_names_and_overwrite(self):
        self.assertFalse(packager.portable_path(Path("memory/CON.txt")))
        self.assertFalse(packager.portable_path(Path("memory/a:b.txt")))
        self.assertTrue(packager.portable_path(Path("memory/中文 帧.png")))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "existing.zip"
            path.write_bytes(b"keep")
            with self.assertRaises(ValueError): packager.package(root, path)
            self.assertEqual(path.read_bytes(), b"keep")
