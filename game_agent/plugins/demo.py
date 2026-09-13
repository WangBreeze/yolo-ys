"""A deterministic game, driven by actual actions rather than a frame script."""

from time import monotonic_ns

from ..contracts import Frame, State
from .base import Plugin


class ShopWorld:
    def __init__(self):
        self.shop_open = False
        self.has_sword = False
        self.equipped = False

    def facts(self):
        return {"shop_open": self.shop_open, "has_sword": self.has_sword,
                "equipped": self.equipped}

    def act(self, action):
        if action.kind != "key":
            return
        if action.key == "B":
            self.shop_open = not self.shop_open
        elif action.key == "1" and self.shop_open:
            self.has_sword = True
        elif action.key == "E" and self.has_sword:
            self.equipped = True


def world(context):
    # The composition context owns this one simulator; no module global state.
    return context.services.setdefault("demo.world", ShopWorld())


class DemoCapture(Plugin):
    ROLE = "capture"
    mode = "simulation"

    def __init__(self, context, options):
        super().__init__(context, options)
        self.world = world(context)
        self.sequence = 0

    def capture(self):
        self.sequence += 1
        return Frame(self.sequence, monotonic_ns(), 640, 360,
                     facts=self.world.facts(), focused=True, window_id="demo-shop")


class FactsPerception(Plugin):
    ROLE = "perception"

    def perceive(self, frame):
        return State(frame.sequence, frame.captured_ns, dict(frame.facts),
                     focused=frame.focused, window_id=frame.window_id)


class DemoController(Plugin):
    ROLE = "controller"
    mode = "simulation"

    def __init__(self, context, options):
        super().__init__(context, options)
        self.world = world(context)

    def execute(self, action, state):
        self.world.act(action)
        return True

    def release_all(self):
        pass


class DryRunController(Plugin):
    ROLE = "controller"
    mode = "dry-run"

    def execute(self, action, state):
        return False

    def release_all(self):
        pass
