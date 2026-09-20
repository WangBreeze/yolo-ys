"""Versioned, reviewable semantic commands between tutorial evidence and Plan."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field

from .contracts import Game, canonical, fingerprint

COMMAND_SCHEMA_VERSION = 1
COMMAND_STATUSES = {"candidate", "reviewed", "rejected"}
FORBIDDEN_INPUT_PARAMS = {"key", "x", "y", "dx", "dy", "duration_ms"}


@dataclass(frozen=True)
class CommandEvidence:
    start_s: float
    end_s: float
    transcript: str
    semantic_segment: int | None = None
    sources: tuple[str, ...] = ("transcript",)
    corrections: tuple[str, ...] = ()

    def __post_init__(self):
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (self.start_s, self.end_s)):
            raise ValueError("command evidence times must be finite numbers")
        if self.start_s < 0 or self.end_s < self.start_s:
            raise ValueError("command evidence needs a valid nonnegative time range")
        if not isinstance(self.transcript, str) or not self.transcript.strip():
            raise ValueError("command evidence needs the original transcript")
        if self.semantic_segment is not None and (type(self.semantic_segment) is not int
                or self.semantic_segment < 0):
            raise ValueError("semantic_segment must be a nonnegative integer")
        if not self.sources or any(not isinstance(v, str) or not v for v in self.sources):
            raise ValueError("command evidence needs named sources")
        if any(not isinstance(v, str) or not v for v in self.corrections):
            raise ValueError("command corrections must be nonempty strings")


@dataclass(frozen=True)
class SemanticCommand:
    id: str
    name: str
    params: dict
    evidence: CommandEvidence
    status: str = "candidate"
    uncertainties: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("semantic command needs an id")
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("semantic command name must be lower snake_case")
        if not isinstance(self.params, dict):
            raise ValueError("semantic command params must be an object")
        forbidden = set(self.params) & FORBIDDEN_INPUT_PARAMS
        if forbidden:
            raise ValueError(f"semantic command cannot contain raw input params: {sorted(forbidden)}")
        if self.status not in COMMAND_STATUSES:
            raise ValueError(f"unsupported command review status: {self.status}")
        if not isinstance(self.evidence, CommandEvidence):
            raise ValueError("semantic command evidence is invalid")
        if any(not isinstance(v, str) or not v for v in self.uncertainties):
            raise ValueError("command uncertainties must be nonempty strings")
        canonical(asdict(self))

    @classmethod
    def from_dict(cls, data: dict) -> SemanticCommand:
        data = dict(data)
        evidence = dict(data["evidence"])
        evidence["sources"] = tuple(evidence.get("sources", ("transcript",)))
        evidence["corrections"] = tuple(evidence.get("corrections", ()))
        data["evidence"] = CommandEvidence(**evidence)
        data["uncertainties"] = tuple(data.get("uncertainties", ()))
        return cls(**data)


@dataclass(frozen=True)
class CommandBundle:
    game: Game
    source: dict
    lexicon: dict
    commands: tuple[SemanticCommand, ...]
    provenance: dict = field(default_factory=dict)
    status: str = "candidate_commands"
    schema_version: int = COMMAND_SCHEMA_VERSION

    def __post_init__(self):
        if self.schema_version != COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported semantic-command schema version")
        if self.status != "candidate_commands":
            raise ValueError("command bundle must remain candidate_commands before review")
        if not isinstance(self.source, dict) or not isinstance(self.source.get("path"), str):
            raise ValueError("command bundle needs source path metadata")
        duration = self.source.get("duration_s")
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("command bundle needs a positive source duration")
        if not isinstance(self.lexicon, dict) or not all(self.lexicon.get(k) for k in ("id", "version")):
            raise ValueError("command bundle needs lexicon id and version")
        if not isinstance(self.provenance, dict):
            raise ValueError("command provenance must be an object")
        if len({command.id for command in self.commands}) != len(self.commands):
            raise ValueError("duplicate semantic command id")
        if any(command.evidence.end_s > duration for command in self.commands):
            raise ValueError("command evidence exceeds source duration")
        canonical(asdict(self))

    @classmethod
    def from_dict(cls, data: dict) -> CommandBundle:
        data = dict(data)
        data["game"] = Game(**data["game"])
        data["commands"] = tuple(SemanticCommand.from_dict(row) for row in data.get("commands", ()))
        return cls(**data)

    @property
    def id(self) -> str:
        return fingerprint(asdict(self))
