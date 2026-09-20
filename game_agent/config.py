from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import Game


@dataclass
class Context:
    root: Path
    config: dict
    services: dict[str, Any] = field(default_factory=dict)

    @property
    def game(self) -> Game:
        return Game(**self.config["game"])

    @property
    def mode(self) -> str:
        return self.config["runtime"]["mode"]

    def input_path(self, value: str) -> Path:
        if not isinstance(value, str) or "://" in value:
            raise ValueError("use a local filesystem path")
        return (Path(self.root).resolve() / value).resolve()

    def output_path(self, value: str) -> Path:
        root = Path(self.root).resolve()
        path = self.input_path(value)
        if not path.is_relative_to(root):
            raise ValueError("outputs must remain inside this project")
        return path


def _read_config(path, seen):
    if path in seen:
        raise ValueError("configuration inheritance cycle")
    seen.add(path)
    with path.open("rb") as f:
        own = tomllib.load(f)
    data = _read_config((path.parent / own.pop("extends")).resolve(), seen) if "extends" in own else {}
    if "project_root" in own:
        own["project_root"] = str((path.parent / own["project_root"]).resolve())
    elif not data:
        own["project_root"] = str(path.parent)

    def merge(base, update):
        for key, value in update.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                # Changing a plugin must not inherit another adapter's options.
                if "use" in value and value["use"] != base[key].get("use"):
                    base[key] = value
                else:
                    merge(base[key], value)
            else:
                base[key] = value
    merge(data, own)
    return data


def load_config(path: str | Path) -> Context:
    path = Path(path).resolve()
    data = _read_config(path, set())
    if data.get("schema_version") != 1:
        raise ValueError("unsupported config schema_version")
    root = (path.parent / data.get("project_root", ".")).resolve()
    if not root.is_dir():
        raise ValueError("project_root must exist")
    Game(**data["game"])
    runtime = data["runtime"]
    if runtime["mode"] not in {"simulation", "replay", "live"}:
        raise ValueError("mode must be simulation, replay or live")
    bounds = {"max_ticks": (1, 100000), "tick_hz": (1, 120),
              "max_frame_age_ms": (1, 10000), "max_action_ms": (1, 1000)}
    for key, (low, high) in bounds.items():
        value = runtime[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"runtime.{key} must be an integer in [{low}, {high}]")
    if not isinstance(runtime.get("allowed_keys"), list) or any(not isinstance(k, str) or not k for k in runtime["allowed_keys"]):
        raise ValueError("runtime.allowed_keys is required")
    context = Context(root, data)
    context.output_path(runtime["stop_file"])
    return context
