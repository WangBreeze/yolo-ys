"""Raw, immutable media objects plus a separate, versioned classification catalog."""

import json
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

from .contracts import canonical, fingerprint
from .media import file_sha256
from .video_contracts import CATEGORIES


def probe(path):
    try:
        process = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=30, check=True)
        data = json.loads(process.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取媒体信息：{Path(path).name}") from exc
    streams = data.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
    return {"video": bool(videos), "audio": any(s.get("codec_type") == "audio" for s in streams),
            "duration_s": float(data.get("format", {}).get("duration", 0)),
            "width": videos[0].get("width", 0) if videos else 0,
            "height": videos[0].get("height", 0) if videos else 0}


class VideoLibrary:
    def __init__(self, context):
        self.context = context
        self.root = context.output_path(context.config.get("video_library", {}).get("path", "memory/videos"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "catalog.sqlite3")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise ValueError("unsupported video catalog schema")
        self.db.execute("CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
        self.db.execute("PRAGMA user_version=1")
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def get(self, asset_id):
        row = self.db.execute("SELECT record FROM assets WHERE id=?", (asset_id,)).fetchone()
        if not row:
            raise ValueError(f"视频编号不存在：{asset_id}")
        return json.loads(row[0])

    def list(self):
        return [json.loads(row[0]) for row in self.db.execute("SELECT record FROM assets ORDER BY rowid DESC")]

    def classify(self, asset_id, category):
        self._category(category)
        row = self.get(asset_id)
        row.update(category=category, category_label=CATEGORIES[category], classification_source="user")
        self._save(row)
        return row

    @staticmethod
    def _category(category):
        if category not in CATEGORIES:
            raise ValueError(f"unknown category: {category}")

    def _save(self, record):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO assets VALUES (?, ?)", (record["id"], canonical(record)))

    def add(self, source, downloader=None, category=None):
        default = self.context.config.get("video_library", {}).get("default_category", "tutorial")
        selected = category or default
        self._category(selected)
        started = time.perf_counter()
        incoming = self.root / "incoming"
        incoming.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=incoming) as directory:
            staging = Path(directory)
            if downloader:
                downloader.download(source, staging)
            else:
                original = self.context.input_path(source)
                if not original.is_file():
                    raise FileNotFoundError(original)
                shutil.copy2(original, staging / original.name)
            media = []
            # Probe streams rather than trusting extensions; skip downloader sidecars.
            for path in sorted(staging.rglob("*")):
                if not path.is_file():
                    continue
                if path.is_symlink() or not path.resolve().is_relative_to(staging):
                    raise ValueError("downloaded file escaped staging directory")
                if path.suffix in {".download", ".part", ".tmp"}:
                    raise ValueError("download contains incomplete media")
                try:
                    info = probe(path)
                except ValueError:
                    continue
                if info["video"] or info["audio"]:
                    media.append({"name": path.relative_to(staging).as_posix(), "sha256": file_sha256(path),
                                  "bytes": path.stat().st_size, **info})
            if not any(m["video"] for m in media):
                raise ValueError("下载没有可读取的视频流；未登记为完成")
            asset_id = fingerprint([(m["name"], m["sha256"]) for m in media])[:20]
            destination = self.root / "objects" / asset_id / "raw"
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staging), str(destination))
            project_root = Path(self.context.root).resolve()
            for item in media:
                item["path"] = (destination / item["name"]).resolve().relative_to(project_root).as_posix()
            existing = self.db.execute("SELECT record FROM assets WHERE id=?", (asset_id,)).fetchone()
            if existing:
                return self.classify(asset_id, selected) if category else json.loads(existing[0])
            record = {"schema_version": 1, "id": asset_id, "source": source,
                      "category": selected, "category_label": CATEGORIES[selected],
                      "classification_source": "user" if category else "default",
                      "media": media, "created_at": time.time(),
                      "acquisition_s": round(time.perf_counter() - started, 4),
                      "original_streams": True}
            self._save(record)
            return record
