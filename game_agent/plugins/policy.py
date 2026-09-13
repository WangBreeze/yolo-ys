import json

from ..contracts import Action, example_key
from .base import Plugin


def resolve_action(template, state):
    values = dict(template)
    target = values.pop("target", None)
    if target is not None:
        boxes = state.targets.get(target, [])
        if len(boxes) != 1:
            raise ValueError(f"target {target!r} must have exactly one observed instance")
        x1, y1, x2, y2 = boxes[0]
        values.update(x=(x1 + x2) / 2, y=(y1 + y2) / 2, target=target)
    return Action(**values)


class TemplatePolicy(Plugin):
    ROLE = "policy"

    def choose(self, step, state):
        return resolve_action(step.action, state)


class ExperiencePolicy(Plugin):
    ROLE = "policy"
    VERSION = "1.0.1"  # UTF-8 model loading, compatible with action-memory schema v1.

    def __init__(self, context, options):
        super().__init__(context, options)
        self.model = json.loads(context.input_path(options["model"]).read_text(encoding="utf-8"))
        if self.model.get("schema_version") != 1 or self.model.get("game_key") != context.game.key:
            raise ValueError("learned policy schema/game/profile mismatch")
        if self.model.get("mode") != context.mode:
            raise ValueError("simulation and live experience cannot be mixed")

    def choose(self, step, state):
        row = self.model["entries"].get(example_key(step.goal, state.facts))
        if row is None:
            raise ValueError("no verified experience for this state; demonstrate it first")
        if row.get("agreement", 0) < self.options.get("min_agreement", 1.0):
            raise ValueError("demonstrations disagree for this state; add context or resolve the ambiguity")
        return resolve_action(row["template"], state)
