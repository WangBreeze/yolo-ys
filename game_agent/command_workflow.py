"""Deterministic extraction and validation of candidate semantic commands."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .command_contracts import CommandBundle, CommandEvidence, SemanticCommand
from .contracts import Game, canonical, fingerprint

LEXICON_SCHEMA_VERSION = 1
EXTRACTOR_VERSION = "1.0.0"


def load_lexicon(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != LEXICON_SCHEMA_VERSION:
        raise ValueError("unsupported command lexicon schema version")
    if not all(isinstance(data.get(k), str) and data[k] for k in ("id", "version", "game_id")):
        raise ValueError("command lexicon needs id, version and game_id")
    commands = data.get("commands")
    if not isinstance(commands, dict) or not commands:
        raise ValueError("command lexicon needs commands")
    seen_aliases = {}
    for name, spec in commands.items():
        SemanticCommand("probe", name, {}, CommandEvidence(0, 0, "probe"))
        if not isinstance(spec, dict) or not isinstance(spec.get("aliases"), list) or not spec["aliases"]:
            raise ValueError(f"command {name} needs aliases")
        if not isinstance(spec.get("allowed_params", []), list):
            raise ValueError(f"command {name} allowed_params must be a list")
        for alias in spec["aliases"]:
            if not isinstance(alias, str) or not alias:
                raise ValueError(f"command {name} has an invalid alias")
            owner = seen_aliases.setdefault(alias, name)
            if owner != name:
                raise ValueError(f"command alias {alias!r} belongs to both {owner} and {name}")
    for field in ("normalizations", "directions", "targets"):
        if not isinstance(data.get(field, {}), dict):
            raise ValueError(f"lexicon {field} must be an object")
    canonical(data)
    return data


def _normalize(text: str, lexicon: dict) -> tuple[str, tuple[str, ...]]:
    normalized = text
    applied = []
    for wrong, right in lexicon.get("normalizations", {}).items():
        if wrong in normalized:
            normalized = normalized.replace(wrong, right)
            applied.append(f"{wrong}→{right}")
    return normalized, tuple(applied)


def _named_matches(text: str, mapping: dict) -> list[str]:
    matches = []
    for name, aliases in mapping.items():
        occurrences = [(text.find(alias), -len(alias)) for alias in aliases if alias in text]
        if occurrences:
            matches.append((min(occurrences), name))
    return [name for _, name in sorted(matches)]


def _semantic_segment(report: dict, start_s: float, end_s: float) -> tuple[int | None, tuple[str, ...]]:
    for index, segment in enumerate(report.get("segments", [])):
        if start_s < segment["end_s"] and end_s > segment["start_s"]:
            uncertainties = tuple(segment.get("uncertainties", [])[:2])
            return index, uncertainties
    return None, ()


def validate_against_lexicon(bundle: CommandBundle, lexicon: dict) -> dict:
    if bundle.game.id != lexicon["game_id"]:
        raise ValueError("command bundle game differs from lexicon")
    for command in bundle.commands:
        if command.name not in lexicon["commands"]:
            raise ValueError(f"unknown semantic command: {command.name}")
        allowed = set(lexicon["commands"][command.name].get("allowed_params", []))
        extra = set(command.params) - allowed
        if extra:
            raise ValueError(f"command {command.name} has unsupported params: {sorted(extra)}")
        required = set(lexicon["commands"][command.name].get("required_params", []))
        missing = required - set(command.params)
        if missing:
            raise ValueError(f"command {command.name} misses params: {sorted(missing)}")
    counts = Counter(command.name for command in bundle.commands)
    return {"ok": True, "bundle_id": bundle.id, "commands": len(bundle.commands),
            "by_name": dict(sorted(counts.items())), "lexicon": bundle.lexicon,
            "status": bundle.status}


def extract_commands(report: dict, lexicon: dict, game: Game) -> CommandBundle:
    if report.get("schema_version") != 1 or report.get("status") != "candidate_understanding":
        raise ValueError("source must be a candidate understanding report schema v1")
    if game.id != lexicon["game_id"]:
        raise ValueError("configured game differs from command lexicon")
    metadata = report.get("metadata", {})
    duration = metadata.get("duration_s")
    audio = report.get("audio", {})
    rows = audio.get("segments")
    if not isinstance(rows, list):
        raise ValueError("source report needs timed audio segments")
    commands = []
    source_hash = metadata.get("sha256") or report.get("cache_key") or fingerprint(report.get("source"))
    for row_index, row in enumerate(rows):
        original = row.get("text", "")
        if not isinstance(original, str) or not original.strip():
            continue
        start_s, end_s = row.get("start_s"), row.get("end_s")
        if type(start_s) not in (int, float) or type(end_s) not in (int, float):
            raise ValueError("audio segment needs numeric start_s and end_s")
        normalized, corrections = _normalize(original, lexicon)
        candidates = []
        for name, spec in lexicon["commands"].items():
            positions = [normalized.find(alias) for alias in spec["aliases"] if alias in normalized]
            if positions:
                candidates.append((min(positions), name, spec))
        segment_index, uncertainties = _semantic_segment(report, start_s, end_s)
        for _, name, spec in sorted(candidates):
            params = {}
            directions = _named_matches(normalized, lexicon.get("directions", {}))
            targets = _named_matches(normalized, lexicon.get("targets", {}))
            if directions and "direction" in spec.get("allowed_params", []):
                params["direction"] = directions[0]
            if targets and "targets" in spec.get("allowed_params", []):
                params["targets"] = targets
            if spec.get("default_target") and "targets" in spec.get("allowed_params", []) and not targets:
                params["targets"] = [spec["default_target"]]
            command_id = fingerprint({"source": source_hash, "row": row_index, "name": name,
                                      "params": params})[:20]
            evidence = CommandEvidence(
                start_s=float(start_s), end_s=float(end_s), transcript=original,
                semantic_segment=segment_index,
                sources=("transcript", "semantic_segment") if segment_index is not None else ("transcript",),
                corrections=corrections)
            commands.append(SemanticCommand(command_id, name, params, evidence,
                                            uncertainties=uncertainties))
    bundle = CommandBundle(
        game=game,
        source={"path": report["source"], "sha256": source_hash, "duration_s": duration,
                "report_cache_key": report.get("cache_key", "")},
        lexicon={"id": lexicon["id"], "version": lexicon["version"]},
        commands=tuple(commands),
        provenance={"extractor": "deterministic-lexicon", "extractor_version": EXTRACTOR_VERSION,
                    "semantic": report.get("provenance", {}).get("semantic", {}),
                    "speech": report.get("provenance", {}).get("audio", {}),
                    "report_schema_version": report["schema_version"]})
    validate_against_lexicon(bundle, lexicon)
    return bundle


def read_bundle(path: Path, lexicon: dict) -> tuple[CommandBundle, dict]:
    bundle = CommandBundle.from_dict(json.loads(path.read_text(encoding="utf-8")))
    return bundle, validate_against_lexicon(bundle, lexicon)


def write_bundle(path: Path, bundle: CommandBundle) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical(asdict(bundle)) + "\n", encoding="utf-8")
    temporary.replace(path)
