"""Additive stage-one API v1; semantic reports are never executable Plans."""

import json
from typing import Protocol

REPORT_SCHEMA = 1
CATEGORIES = {"tutorial": "视频教程", "gameplay": "游戏实录", "reference": "参考资料", "other": "其他"}
PRESETS = {
    "fast": {"frames": 12, "batch_frames": 12, "max_edge": 448, "max_tokens": 700},
    "balanced": {"frames": 32, "batch_frames": 8, "max_edge": 672, "max_tokens": 1000},
    "detailed": {"frames": 64, "batch_frames": 8, "max_edge": 896, "max_tokens": 1400},
}


def validate_description(value):
    if not isinstance(value, dict) or not isinstance(value.get("summary"), str) or not value["summary"].strip():
        raise ValueError("semantic model must return a nonempty summary")
    result = {"summary": value["summary"]}
    for key in ("observations", "operation_intents", "uncertainties"):
        rows = value.get(key)
        if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
            raise ValueError(f"semantic model must return a string list: {key}")
        result[key] = rows
    return result


def parse_description(text):
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return validate_description(json.loads(text))


class Downloader(Protocol):
    def download(self, url: str, destination): ...
    def close(self): ...


class Semantic(Protocol):
    def identity(self) -> dict: ...
    def describe(self, frames, transcript: str, max_tokens: int) -> dict: ...
    def close(self): ...


class Speech(Protocol):
    def identity(self) -> dict: ...
    def transcribe(self, source) -> dict: ...
    def close(self): ...
