#!/usr/bin/env python3
"""Exercise real local YOLO training on synthetic video; never operate a game."""

import argparse
import json
import os
from pathlib import Path
import socket
import sys
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="memory/validation/offline-training")
    args = parser.parse_args()
    os.environ.update(YOLO_OFFLINE="true", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      YOLO_CONFIG_DIR=str(ROOT / "memory/ultralytics"))
    from game_agent.config import load_config
    from game_agent.training_data import prepare, build
    from game_agent.plugins.detector_training import YoloDetectorTrainer
    import cv2
    import numpy as np
    import torch
    torch.set_num_threads(2)
    context = load_config(ROOT / "configs/offline-training.toml")
    context.config["game"] = {"id": "synthetic-detection-check", "version": "1", "profile": "drawn-boxes-v1"}
    directory = context.output_path(args.output)
    directory.mkdir(parents=True, exist_ok=False)
    manifests = []
    for j, split in enumerate(("train", "val")):
        video = directory / f"synthetic-{split}.avi"
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (128, 96))
        if not writer.isOpened():
            raise RuntimeError("cannot create synthetic video")
        for i in range(8):
            pixels = np.full((96, 128, 3), (20 + j * 60, i * 7, 30), dtype=np.uint8)
            cv2.rectangle(pixels, (32, 24), (95, 71), (220, 210, 20), -1)
            writer.write(pixels)
        writer.release()
        result = prepare(context, [str(video)], str(directory / f"annotations-{split}"),
                         ["synthetic_button"], f"synthetic-recording-{j}", split, 4)
        path = Path(result["path"])
        annotation = json.loads(path.read_text(encoding="utf-8"))
        for frame in annotation["frames"]:
            frame.update(reviewed=True, boxes=[{"class": "synthetic_button", "xyxy": [0.25, 0.25, 0.75, 0.75]}])
        path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8")
        manifests.append(str(path))
    dataset = build(context, manifests, str(directory / "dataset"))
    plugin = YoloDetectorTrainer(context, {"weights": "yolo26n.pt", "device": "cpu", "epochs": 1,
                                          "imgsz": 64, "batch": 2, "workers": 0})
    started = perf_counter()
    with patch.object(socket.socket, "connect", side_effect=AssertionError("offline training attempted network access")):
        result = plugin.train(dataset["path"], str(directory / "run"))
    record = {"scope": "synthetic video and CPU YOLO training, not real game accuracy",
              "training_wall_s": perf_counter() - started, "dataset": dataset, "training": result,
              "network_check": "Python socket.connect blocked, not an OS-level audit"}
    (directory / "result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
