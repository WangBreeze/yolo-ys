import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch

from game_agent.config import load_config
from game_agent.plugins.detector_training import YoloDetectorTrainer
from game_agent.training_data import build, child_path, prepare, validate_dataset

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("cv2"), "optional OpenCV")
class TrainingDataTests(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy as np
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.context = load_config(ROOT / "configs/offline-training.toml")
        self.context.root = self.root
        self.manifests = []
        for j, split in enumerate(("train", "val")):
            path = self.root / f"clip{j}.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
            self.assertTrue(writer.isOpened())
            for i in range(5):
                writer.write(np.full((48, 64, 3), 20 + i * 10 + j * 100, dtype=np.uint8))
            writer.release()
            result = prepare(self.context, [str(path)], f"annotation{j}", ["使用按钮"], f"session{j}", split, 2)
            self.manifests.append(result["path"])

    def review(self, transform=None):
        for manifest in self.manifests:
            path = Path(manifest)
            data = json.loads(path.read_text(encoding="utf-8"))
            for row in data["frames"]:
                row.update(reviewed=True, boxes=[{"class": "使用按钮", "xyxy": [0.1, 0.2, 0.5, 0.8]}])
                if transform: transform(row)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_unreviewed_frames_cannot_become_training_data(self):
        data = json.loads(Path(self.manifests[0]).read_text(encoding="utf-8"))
        self.assertEqual(data["evidence"], "video_only_no_action_labels")
        self.assertFalse(data["frames"][0]["reviewed"])
        with self.assertRaisesRegex(ValueError, "reviewed=true"):
            build(self.context, self.manifests, "dataset")
        self.assertFalse((self.root / "dataset").exists())

    def test_reviewed_dataset_is_portable_and_normalizes_labels(self):
        self.review()
        result = build(self.context, self.manifests, "dataset")
        path, data = validate_dataset(self.context, result["path"])
        self.assertEqual(data["counts"], {"train": 2, "val": 2, "test": 0})
        label = self.root / "dataset" / data["frames"][0]["label"]
        self.assertEqual(label.read_text().strip(), "0 0.30000000 0.50000000 0.40000000 0.60000000")
        self.assertNotIn(str(self.root), (path.parent / "data.yaml").read_text(encoding="utf-8"))
        moved = self.root / "迁移后的目录"
        shutil.move(str(path.parent), moved)
        validate_dataset(self.context, str(moved / "dataset.json"))

    def test_same_recording_cannot_cross_train_and_validation(self):
        self.review(lambda row: row.update(group="same-session"))
        with self.assertRaisesRegex(ValueError, "leakage"):
            build(self.context, self.manifests, "dataset")

    def test_same_source_cannot_evade_split_guard_by_renaming_group(self):
        self.review(lambda row: row.update(source_sha256="same-source"))
        with self.assertRaisesRegex(ValueError, "leakage"):
            build(self.context, self.manifests, "dataset")

    def test_out_of_range_or_reversed_box_is_rejected(self):
        self.review(lambda row: row.update(boxes=[{"class": "使用按钮", "xyxy": [0.5, 0, 0.1, 1]}]))
        with self.assertRaisesRegex(ValueError, "positive area"):
            build(self.context, self.manifests, "dataset")

    def test_paths_cannot_escape_or_use_windows_drive(self):
        for path in ("../secret", "C:/secret", "C:\\secret", "/tmp/secret"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                child_path(self.root, path)

    def test_changed_images_or_labels_fail_validation(self):
        self.review()
        result = build(self.context, self.manifests, "dataset")
        _, data = validate_dataset(self.context, result["path"])
        label = self.root / "dataset" / data["frames"][0]["label"]
        label.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            validate_dataset(self.context, result["path"])

    def test_validation_requires_an_independent_recording(self):
        self.review()
        with self.assertRaisesRegex(ValueError, "validation"):
            build(self.context, self.manifests[:1], "dataset")

    def test_existing_annotations_are_never_overwritten(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare(self.context, ["clip0.avi"], "annotation0", ["使用按钮"], "session0")

    def test_trainer_uses_local_reviewed_data_and_records_portable_artifact(self):
        self.review()
        result = build(self.context, self.manifests, "dataset")
        (self.root / "initial.pt").write_bytes(b"fake local weight")
        calls = []
        class FakeYOLO:
            def __init__(inner, weights, task): calls.append((weights, task))
            def train(inner, **kw):
                calls.append(kw)
                dest = Path(kw["project"]) / kw["name"]
                (dest / "weights").mkdir(parents=True)
                (dest / "weights/best.pt").write_bytes(b"trained fake")
                inner.trainer = types.SimpleNamespace(save_dir=dest)
                return types.SimpleNamespace(results_dict={"metrics/mAP50(B)": 0.5})
        plugin = YoloDetectorTrainer(self.context, {"weights": "initial.pt", "epochs": 1})
        with patch.dict("sys.modules", {"ultralytics": types.SimpleNamespace(YOLO=FakeYOLO)}), patch.dict("os.environ", {}):
            report = plugin.train(result["path"], "training/run1")
        self.assertFalse(calls[1]["amp"])
        self.assertEqual(calls[1]["workers"], 0)
        self.assertEqual(report["status"], "trained_not_game_verified")
        artifact = json.loads((self.root / "training/run1/training.json").read_text(encoding="utf-8"))
        self.assertEqual(artifact["weights"], "weights/best.pt")
