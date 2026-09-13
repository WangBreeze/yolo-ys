"""Lazy plugin loading. Changing an adapter does not import its competitors."""

import importlib
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from .contracts import API_VERSION

METHODS = {
    "capture": ("capture",), "perception": ("perceive",),
    "planner": ("decide",), "policy": ("choose",),
    "controller": ("execute", "release_all"), "tutorial": ("analyze",),
    "learner": ("train",),
    "detector_trainer": ("train",),
    "downloader": ("download",), "semantic": ("describe", "identity"),
    "speech": ("transcribe", "identity"),
    "memory": ("remember", "recall", "load_plan", "begin", "append", "finish", "examples", "export_run"),
}


@dataclass(frozen=True)
class PluginSpec:
    id: str
    role: str
    version: str
    api_version: int
    factory: str


class Registry:
    def __init__(self):
        self.specs: dict[str, PluginSpec] = {}

    def add(self, spec: PluginSpec):
        if spec.id in self.specs:
            raise ValueError(f"duplicate plugin id: {spec.id}")
        if spec.role not in METHODS or spec.api_version != API_VERSION:
            raise ValueError(f"incompatible plugin API/role: {spec.id}")
        if ":" not in spec.factory or not spec.version:
            raise ValueError(f"invalid plugin manifest: {spec.id}")
        self.specs[spec.id] = spec

    def read(self, path: Path):
        with path.open("rb") as f:
            for row in tomllib.load(f).get("plugins", []):
                self.add(PluginSpec(**row))

    def create(self, role, context):
        selection = context.config["plugins"][role]
        spec = self.specs[selection["use"]]
        if spec.role != role:
            raise ValueError(f"{spec.id} does not provide {role}")
        module, name = spec.factory.split(":", 1)
        cls = getattr(importlib.import_module(module), name)
        if (getattr(cls, "API_VERSION", None), getattr(cls, "ROLE", None), getattr(cls, "VERSION", None)) != (spec.api_version, role, spec.version):
            raise ValueError(f"plugin manifest/class mismatch: {spec.id}")
        for method in (*METHODS[role], "close"):
            if not callable(getattr(cls, method, None)):
                raise TypeError(f"{spec.id} is missing {method}")
        return cls(context, selection.get("options", {}))

    def provenance(self, context) -> dict:
        return {role: asdict(self.specs[item["use"]])
                for role, item in context.config["plugins"].items()}


def registry_for(context):
    registry = Registry()
    registry.read(Path(__file__).parent / "plugins" / "manifest.toml")
    for path in context.config.get("plugin_manifests", []):
        registry.read(context.input_path(path))
    return registry
