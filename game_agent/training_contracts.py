"""Additive plugin API v1 role; does not alter action Learner or memory schemas."""

from typing import Protocol


class DetectorTrainer(Protocol):
    def train(self, source: str, output: str) -> dict: ...
    def close(self) -> None: ...
