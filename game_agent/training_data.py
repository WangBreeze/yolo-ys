"""Offline, reviewed video-frame datasets. No game input or inferred action labels."""

import json
import math
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from .contracts import canonical
from .media import file_sha256, sample_video

SCHEMA = 1
SPLITS = {"train", "val", "test", "unassigned"}


def classes_valid(classes):
    if (not isinstance(classes, list) or not classes
            or any(not isinstance(c, str) or not c.strip() or c.startswith("__") for c in classes)
            or len(set(classes)) != len(classes)):
        raise ValueError("classes must be unique nonempty labels, without the reserved __ prefix")


def child_path(root, value):
    # Saved datasets use POSIX relative paths on both platforms; reject Windows drives too.
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("dataset paths must be portable relative paths")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("dataset path escapes its directory")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("dataset path escapes its directory")
    return path


def prepare(context, sources, output, classes, group, split="unassigned", frames=32):
    classes_valid(classes)
    if not isinstance(group, str) or not group.strip() or split not in SPLITS:
        raise ValueError("a recording/session group and valid split are required")
    destination = context.output_path(output)
    if destination.exists():
        raise ValueError("dataset output already exists; choose a new version directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # This is an explicit training-data operation; the video-library originals are untouched.
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        staging = Path(directory)
        (staging / "images").mkdir()
        rows, recordings, seen = [], [], set()
        for source in sources:
            path = context.input_path(source)
            if not path.is_file():
                from .video_library import VideoLibrary
                with VideoLibrary(context) as library:
                    asset = library.get(source)
                videos = [m for m in asset["media"] if m["video"]]
                if len(videos) != 1:
                    raise ValueError("select a single video part by its local path")
                path = context.input_path(videos[0]["path"])
            metadata, samples = sample_video(path, frames)
            digest = metadata["sha256"]
            if digest in seen:
                raise ValueError("duplicate source video")
            seen.add(digest)
            # Identity is content based, not tied to a Linux filesystem location.
            recordings.append({"sha256": digest, "name": path.name, "group": group,
                               "duration_s": metadata["duration_s"], "fps": metadata["fps"]})
            import cv2
            for time_s, pixels in samples:
                index = round(time_s * metadata["fps"])
                name = f"{digest[:20]}_{index:09d}"
                relative = f"images/{name}.png"
                ok, encoded = cv2.imencode(".png", pixels)
                if not ok:
                    raise ValueError("could not encode dataset frame")
                target = staging / relative
                target.write_bytes(encoded.tobytes())  # Unicode paths work on Windows too.
                height, width = pixels.shape[:2]
                rows.append({"id": name, "image": relative, "image_sha256": file_sha256(target),
                             "source_sha256": digest, "group": group, "time_s": time_s,
                             "width": width, "height": height, "split": split,
                             "reviewed": False, "boxes": []})
        manifest = {"schema_version": SCHEMA, "kind": "video_detection_annotations",
                    "game": asdict(context.game), "classes": classes, "sources": recordings,
                    "evidence": "video_only_no_action_labels", "frames": rows}
        (staging / "annotations.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
        (staging / "README.txt").write_text(
            "填写 annotations.json：每帧 boxes=[{\"class\":\"类别名\",\"xyxy\":[左,上,右,下]}]。\n"
            "坐标为 0–1 的归一化值。核对整帧后设置 reviewed=true；明确无目标的负样本才允许空 boxes。\n"
            "split 设为 train/val/test。来自同一游戏录制场次的 group 必须保持同一集合。\n"
            "这里没有真实键鼠事件；不得作为动作模仿或已完成任务的真值。\n", encoding="utf-8")
        staging.rename(destination)
    return {"path": str(destination / "annotations.json"), "frames": len(rows),
            "status": "needs_annotation", "action_labels": False}


def _annotations(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA or data.get("kind") != "video_detection_annotations":
        raise ValueError("unsupported annotation schema")
    classes_valid(data["classes"])
    if not isinstance(data.get("frames"), list) or not data["frames"]:
        raise ValueError("annotation document has no frames")
    return data


def build(context, manifests, output):
    destination = context.output_path(output)
    if destination.exists():
        raise ValueError("dataset output already exists; choose a new version directory")
    rows, known_ids, groups, sources, image_splits = [], set(), {}, {}, {}
    classes, game = None, None
    counts = {s: 0 for s in ("train", "val", "test")}
    for value in manifests:
        path = context.input_path(value)
        data = _annotations(path)
        if classes is None:
            classes, game = data["classes"], data["game"]
        if data["classes"] != classes or data["game"] != game or game != asdict(context.game):
            raise ValueError("all annotation classes and game/version/profile must match this config")
        for row in data["frames"]:
            split = row.get("split")
            if row.get("reviewed") is not True or split not in counts:
                raise ValueError(f"frame {row.get('id')} needs reviewed=true and train/val/test split")
            group, source = row.get("group"), row.get("source_sha256")
            if not group or not source:
                raise ValueError("every frame needs a recording group and source SHA-256")
            image = child_path(path.parent, row["image"])
            digest = file_sha256(image)
            if digest != row["image_sha256"]:
                raise ValueError("frame bytes changed after annotation; review the frame again")
            for key, mapping in ((group, groups), (source, sources), (digest, image_splits)):
                if key in mapping and mapping[key] != split:
                    raise ValueError("train/val/test leakage: a recording, source or duplicate image crosses splits")
                mapping[key] = split
            identifier = row["id"]
            if (not isinstance(identifier, str) or not identifier
                    or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in identifier)):
                raise ValueError("frame id must be portable ASCII")
            if identifier in known_ids:
                raise ValueError("duplicate frame id")
            known_ids.add(identifier)
            labels = []
            if not isinstance(row.get("boxes"), list):
                raise ValueError("boxes must be a list; [] denotes a reviewed negative frame")
            for box in row["boxes"]:
                if not isinstance(box, dict) or box.get("class") not in classes:
                    raise ValueError("unknown annotation class")
                xyxy = box.get("xyxy")
                if (not isinstance(xyxy, list) or len(xyxy) != 4
                        or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in xyxy)):
                    raise ValueError("boxes need finite normalized xyxy coordinates")
                x1, y1, x2, y2 = xyxy
                if x1 >= x2 or y1 >= y2:
                    raise ValueError("annotation box must have positive area")
                labels.append(f"{classes.index(box['class'])} {(x1+x2)/2:.8f} {(y1+y2)/2:.8f} {x2-x1:.8f} {y2-y1:.8f}")
            rows.append((row, image, labels))
            counts[split] += 1
    if not counts["train"] or not counts["val"]:
        raise ValueError("need separately recorded, reviewed training AND validation data")
    if not any(labels for row, _, labels in rows if row["split"] == "train"):
        raise ValueError("training data has no labeled target boxes")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        staging = Path(directory)
        items = []
        for row, source, labels in rows:
            image = staging / "images" / row["split"] / f"{row['id']}.png"
            label = staging / "labels" / row["split"] / f"{row['id']}.txt"
            image.parent.mkdir(parents=True, exist_ok=True)
            label.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, image)
            label.write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")
            items.append({"image": image.relative_to(staging).as_posix(),
                          "label": label.relative_to(staging).as_posix(),
                          "image_sha256": file_sha256(image), "label_sha256": file_sha256(label),
                          "split": row["split"], "group": row["group"],
                          "source_sha256": row["source_sha256"], "time_s": row["time_s"]})
        # Omit `path`: Ultralytics resolves relative entries against this YAML location.
        yaml = ["train: images/train", "val: images/val"]
        if counts["test"]:
            yaml.append("test: images/test")
        yaml.append("names:")
        yaml += [f"  {i}: {json.dumps(name, ensure_ascii=False)}" for i, name in enumerate(classes)]
        (staging / "data.yaml").write_text("\n".join(yaml) + "\n", encoding="utf-8")
        dataset = {"schema_version": SCHEMA, "kind": "reviewed_detection_dataset", "game": game,
                   "classes": classes, "counts": counts, "frames": items,
                   "yaml_sha256": file_sha256(staging / "data.yaml"),
                   "evidence": "reviewed_video_boxes_no_action_labels"}
        (staging / "dataset.json").write_text(canonical(dataset) + "\n", encoding="utf-8")
        staging.rename(destination)
    return {"path": str(destination / "dataset.json"), "counts": counts, "classes": classes}


def validate_dataset(context, source):
    path = context.input_path(source)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA or data.get("kind") != "reviewed_detection_dataset":
        raise ValueError("use a reviewed dataset produced by build-dataset")
    if data.get("game") != asdict(context.game):
        raise ValueError("dataset game/version/profile differs from this configuration")
    classes_valid(data["classes"])
    frames = data.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("reviewed dataset has no frames")
    counts = {s: 0 for s in ("train", "val", "test")}
    groups, sources, images = {}, {}, {}
    names = set()
    if file_sha256(path.parent / "data.yaml") != data["yaml_sha256"]:
        raise ValueError("dataset YAML changed after review")
    for row in frames:
        split = row.get("split")
        if split not in counts or not row.get("group") or not row.get("source_sha256"):
            raise ValueError("invalid dataset split/recording provenance")
        counts[split] += 1
        for field in ("image", "label"):
            if not row[field].startswith(f"{field}s/{split}/") or row[field].casefold() in names:
                raise ValueError("dataset file path does not match its split or is duplicated")
            names.add(row[field].casefold())
        for key, mapping in ((row["group"], groups), (row["source_sha256"], sources),
                             (row["image_sha256"], images)):
            if key in mapping and mapping[key] != split:
                raise ValueError("train/val/test leakage in dataset manifest")
            mapping[key] = split
        for kind in ("image", "label"):
            if file_sha256(child_path(path.parent, row[kind])) != row[kind + "_sha256"]:
                raise ValueError(f"dataset {kind} changed after review")
    if counts != data.get("counts") or not counts["train"] or not counts["val"]:
        raise ValueError("dataset needs consistent nonempty training and validation splits")
    return path, data
