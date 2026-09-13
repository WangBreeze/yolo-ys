"""Optional local YOLO training; independent of action-memory learning."""

import os
from dataclasses import asdict

from ..contracts import canonical
from ..media import file_sha256
from ..training_data import validate_dataset
from .base import Plugin


class YoloDetectorTrainer(Plugin):
    ROLE = "detector_trainer"

    def train(self, source, output):
        dataset_path, dataset = validate_dataset(self.context, source)
        weights = self.context.input_path(self.options.get("weights", "yolo26n.pt"))
        if not weights.is_file():
            raise ValueError("prepare local .pt weights before training; no automatic download")
        destination = self.context.output_path(output)
        if destination.exists():
            raise ValueError("training output already exists; choose a new run directory")
        options = {"epochs": self.options.get("epochs", 50), "imgsz": self.options.get("imgsz", 640),
                   "batch": self.options.get("batch", 8), "workers": self.options.get("workers", 0),
                   "device": self.options.get("device", "cpu"), "seed": self.options.get("seed", 0)}
        for key in ("epochs", "imgsz", "batch"):
            if type(options[key]) is not int or options[key] <= 0:
                raise ValueError(f"{key} must be a positive integer")
        if type(options["workers"]) is not int or options["workers"] < 0:
            raise ValueError("workers must be a nonnegative integer")
        os.environ["YOLO_OFFLINE"] = "true"
        local_config = self.context.output_path("memory/ultralytics")
        local_config.mkdir(parents=True, exist_ok=True)
        os.environ["YOLO_CONFIG_DIR"] = str(local_config)
        from ultralytics import YOLO
        model = YOLO(str(weights), task="detect")
        # amp=False avoids Ultralytics' auxiliary AMP-check model download.
        metrics = model.train(data=str(dataset_path.parent / "data.yaml"), project=str(destination.parent),
                              name=destination.name, exist_ok=False, pretrained=True,
                              amp=False, plots=False, **options)
        actual = model.trainer.save_dir.resolve()
        best = actual / "weights" / "best.pt"
        if not best.is_file():
            raise RuntimeError("training did not produce weights/best.pt")
        report = {"schema_version": 1, "kind": "detector_training", "status": "trained_not_game_verified",
                  "game": asdict(self.context.game), "classes": dataset["classes"],
                  "dataset_sha256": file_sha256(dataset_path), "initial_weights_sha256": file_sha256(weights),
                  "weights": "weights/best.pt", "weights_sha256": file_sha256(best),
                  "options": options, "plugin": "yolo.detector-trainer", "plugin_version": self.VERSION,
                  "metrics": {k: float(v) for k, v in getattr(metrics, "results_dict", {}).items()}}
        (actual / "training.json").write_text(canonical(report) + "\n", encoding="utf-8")
        return {**report, "path": str(actual / "training.json"), "weights_path": str(best)}
