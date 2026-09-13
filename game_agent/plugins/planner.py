from ..contracts import Decision, matches
from .base import Plugin


class SequentialPlanner(Plugin):
    ROLE = "planner"

    def __init__(self, context, options):
        super().__init__(context, options)
        self.index = 0
        self.started_ns = None
        self.last_action_ns = None
        self.attempts = 0
        self.confirmed = 0
        self.confirmation_frames = options.get("confirmation_frames", 2)
        if type(self.confirmation_frames) is not int or not 1 <= self.confirmation_frames <= 30:
            raise ValueError("confirmation_frames must be in [1, 30]")

    def decide(self, plan, state, now_ns):
        if self.index == len(plan.steps):
            if matches(state.facts, plan.success):
                return Decision("complete")
            return Decision("blocked", reason="final success conditions are not observed")
        step = plan.steps[self.index]
        if self.started_ns is None:
            self.started_ns = now_ns
        if matches(state.facts, step.post):
            self.confirmed += 1
            if self.confirmed < self.confirmation_frames:
                return Decision("wait", step, "confirming postconditions across frames")
            self.index += 1
            self.started_ns = self.last_action_ns = None
            self.attempts = 0
            self.confirmed = 0
            return Decision("advance", step)
        self.confirmed = 0
        if (now_ns - self.started_ns) / 1e9 >= step.timeout_s:
            return Decision("blocked", step, "step timed out")
        if not matches(state.facts, step.pre):
            return Decision("wait", step, "waiting for preconditions")
        if self.last_action_ns is not None and (now_ns - self.last_action_ns) / 1e6 < step.retry_ms:
            return Decision("wait", step, "waiting for observed action result")
        if self.attempts >= step.max_attempts:
            return Decision("blocked", step, "action attempts exhausted")
        self.attempts += 1
        self.last_action_ns = now_ns
        return Decision("act", step)
