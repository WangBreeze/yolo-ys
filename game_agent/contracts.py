"""Versioned data at plugin boundaries; payload pixels never enter JSON logs."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

API_VERSION = 1


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def matches(facts: dict, expected: dict) -> bool:
    # Missing facts are unknown, including when the expected value is false.
    return all(k in facts and type(facts[k]) is type(v) and facts[k] == v
               for k, v in expected.items())


def example_key(goal, facts):
    semantic = {k: v for k, v in facts.items() if not k.startswith("__")}
    return fingerprint({"goal": goal, "facts": semantic})


@dataclass(frozen=True)
class Game:
    id: str
    version: str
    profile: str

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in asdict(self).values()):
            raise ValueError("game id/version/profile must be nonempty strings")

    @property
    def key(self) -> str:
        return fingerprint(asdict(self))


@dataclass(frozen=True)
class Action:
    kind: str
    key: str = ""
    x: float | None = None
    y: float | None = None
    dx: int = 0
    dy: int = 0
    duration_ms: int = 50
    target: str = ""

    def __post_init__(self):
        if self.kind not in {"key", "click", "move", "wait"}:
            raise ValueError(f"unsupported action: {self.kind}")
        if type(self.duration_ms) is not int or not 0 <= self.duration_ms <= 1000:
            raise ValueError("duration_ms must be an integer in [0, 1000]")
        if self.kind == "key" and (not isinstance(self.key, str) or not self.key):
            raise ValueError("key action needs a key")
        if self.kind == "click":
            if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
                   for v in (self.x, self.y)):
                raise ValueError("click uses normalized window coordinates in [0, 1]")
        if any(type(v) is not int or abs(v) > 2000 for v in (self.dx, self.dy)):
            raise ValueError("relative mouse movement must be bounded integers")

    def template(self):
        if self.kind == "click" and self.target:
            return {"kind": "click", "target": self.target, "duration_ms": self.duration_ms}
        values = asdict(self)
        values.pop("target")
        return values


@dataclass(frozen=True)
class Step:
    id: str
    goal: str
    pre: dict
    post: dict
    action: dict
    timeout_s: float = 5
    max_attempts: int = 2
    retry_ms: int = 500
    source_seconds: float | None = None

    def __post_init__(self):
        if not self.id or not self.goal or not isinstance(self.pre, dict):
            raise ValueError("step needs id, goal and preconditions")
        if not isinstance(self.post, dict) or not self.post:
            raise ValueError("every step needs observable postconditions")
        if not isinstance(self.action, dict):
            raise ValueError("step action must be an object")
        if "target" in self.action:
            if set(self.action) - {"kind", "target", "duration_ms"} or self.action.get("kind") != "click":
                raise ValueError("target action must be a click with a target label")
            if not isinstance(self.action["target"], str) or not self.action["target"]:
                raise ValueError("target label must not be empty")
            Action("click", x=0.5, y=0.5, duration_ms=self.action.get("duration_ms", 50))
        else:
            Action(**self.action)
        if not isinstance(self.timeout_s, (int, float)) or not math.isfinite(self.timeout_s) or not 0 < self.timeout_s <= 300:
            raise ValueError("timeout_s must be in (0, 300]")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 20:
            raise ValueError("max_attempts must be in [1, 20]")
        if type(self.retry_ms) is not int or not 0 <= self.retry_ms <= 10000:
            raise ValueError("retry_ms must be in [0, 10000]")
        if self.source_seconds is not None and (type(self.source_seconds) not in (int, float)
                or not math.isfinite(self.source_seconds) or self.source_seconds < 0):
            raise ValueError("source_seconds must be a nonnegative finite number")


@dataclass(frozen=True)
class Plan:
    game: Game
    title: str
    steps: tuple[Step, ...]
    success: dict
    provenance: dict = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self):
        if self.schema_version != 1 or not isinstance(self.title, str) or not self.title:
            raise ValueError("invalid plan version/title")
        if not self.steps or len(self.steps) > 200 or not isinstance(self.success, dict) or not self.success:
            raise ValueError("plan needs 1..200 steps and observable success conditions")
        if len({s.id for s in self.steps}) != len(self.steps):
            raise ValueError("duplicate step id")
        if not isinstance(self.provenance, dict):
            raise ValueError("plan provenance must be an object")
        canonical(asdict(self))

    @classmethod
    def from_dict(cls, data: dict) -> Plan:
        data = dict(data)
        data["game"] = Game(**data["game"])
        data["steps"] = tuple(Step(**s) for s in data["steps"])
        return cls(**data)

    @property
    def id(self) -> str:
        return fingerprint(asdict(self))


@dataclass
class Frame:
    sequence: int
    captured_ns: int
    width: int
    height: int
    pixels: Any = field(default=None, repr=False)
    facts: dict = field(default_factory=dict)
    focused: bool = False
    window_id: str = ""


@dataclass(frozen=True)
class State:
    sequence: int
    captured_ns: int
    facts: dict
    targets: dict = field(default_factory=dict)
    focused: bool = False
    window_id: str = ""


@dataclass(frozen=True)
class Decision:
    status: str  # act, wait, advance, complete, blocked
    step: Step | None = None
    reason: str = ""


class Capture(Protocol):
    mode: str
    def capture(self) -> Frame | None: ...
    def close(self) -> None: ...


class Perception(Protocol):
    def perceive(self, frame: Frame) -> State: ...
    def close(self) -> None: ...


class Planner(Protocol):
    def decide(self, plan: Plan, state: State, now_ns: int) -> Decision: ...
    def close(self) -> None: ...


class Policy(Protocol):
    def choose(self, step: Step, state: State) -> Action: ...
    def close(self) -> None: ...


class Controller(Protocol):
    mode: str
    def execute(self, action: Action, state: State) -> bool: ...
    def release_all(self) -> None: ...
    def close(self) -> None: ...


class Tutorial(Protocol):
    def analyze(self, source: str) -> Plan: ...
    def close(self) -> None: ...


class Learner(Protocol):
    def train(self, examples: list[dict], output: str) -> dict: ...
    def close(self) -> None: ...


class Memory(Protocol):
    def remember(self, plan: Plan) -> str: ...
    def recall(self, query: str, game: Game, mode: str) -> list[dict]: ...
    def load_plan(self, plan_id: str, game: Game) -> Plan: ...
    def begin(self, plan: Plan, mode: str, plugins: dict) -> str: ...
    def append(self, run_id: str, kind: str, data: dict) -> None: ...
    def finish(self, run_id: str, status: str, reason: str) -> None: ...
    def examples(self, game: Game, mode: str) -> list[dict]: ...
    def export_run(self, run_id: str, path: Any) -> None: ...
    def close(self) -> None: ...
