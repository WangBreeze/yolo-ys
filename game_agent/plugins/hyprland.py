"""A portable baseline on Hyprland; grim/PPM avoids JPEG but is not zero-copy."""

import json
import subprocess
from time import monotonic, monotonic_ns, sleep

from ..contracts import Frame
from .base import Plugin


def active_window():
    result = subprocess.run(["hyprctl", "-j", "activewindow"], check=True,
                            capture_output=True, timeout=2)
    return json.loads(result.stdout)


def check_window(window, options, expected_id=None):
    if not options.get("window_class") or window.get("class") != options["window_class"]:
        raise ValueError("configured game window is not focused")
    if options.get("window_title") and window.get("title") != options["window_title"]:
        raise ValueError("game window title mismatch")
    if not window.get("address") or (expected_id and window["address"] != expected_id):
        raise ValueError("target game window changed")
    if len(window.get("at", [])) != 2 or len(window.get("size", [])) != 2:
        raise ValueError("invalid game window geometry")
    return [*window["at"], *window["size"]]


class HyprlandCapture(Plugin):
    ROLE = "capture"
    mode = "live"

    def __init__(self, context, options):
        super().__init__(context, options)
        if not options.get("window_class"):
            raise ValueError("window_class must be explicitly configured")
        self.sequence = 0

    def capture(self):
        import cv2
        import numpy as np
        captured_ns = monotonic_ns()
        window = active_window()
        x, y, w, h = check_window(window, self.options)
        result = subprocess.run(["grim", "-t", "ppm", "-g", f"{x},{y} {w}x{h}", "-"],
                                check=True, capture_output=True, timeout=2)
        pixels = cv2.imdecode(np.frombuffer(result.stdout, dtype=np.uint8), cv2.IMREAD_COLOR)
        if pixels is None:
            raise ValueError("screen capture decoding failed")
        current = active_window()
        if check_window(current, self.options, window["address"]) != [x, y, w, h]:
            raise ValueError("window moved during capture")
        self.sequence += 1
        ph, pw = pixels.shape[:2]
        return Frame(self.sequence, captured_ns, pw, ph, pixels,
                     {"__window_rect": [x, y, w, h]}, True, window["address"])


class UInputController(Plugin):
    ROLE = "controller"
    mode = "live"

    def __init__(self, context, options):
        super().__init__(context, options)
        if not context.services.get("live_enabled") or not options.get("window_class"):
            raise ValueError("uinput needs --live and window_class")
        from evdev import UInput, ecodes
        self.ecodes = ecodes
        self.keys = {}
        for name in context.config["runtime"]["allowed_keys"]:
            code = getattr(ecodes, "KEY_" + name.upper(), None)
            if code is None:
                raise ValueError(f"unsupported evdev key: {name}")
            self.keys[name] = code
        self.held = set()
        self.device = UInput({ecodes.EV_KEY: [*self.keys.values(), ecodes.BTN_LEFT],
                              ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y]}, name="local-game-agent")

    def check(self, state):
        if self.context.output_path(self.context.config["runtime"]["stop_file"]).exists():
            raise ValueError("stop file present")
        rect = check_window(active_window(), self.options, state.window_id)
        if rect != state.facts.get("__window_rect"):
            raise ValueError("window geometry changed since observation")
        age_ms = (monotonic_ns() - state.captured_ns) / 1e6
        if age_ms < 0 or age_ms > self.context.config["runtime"]["max_frame_age_ms"]:
            raise ValueError("observation expired before/during input")
        return rect

    def execute(self, action, state):
        rect = self.check(state)
        ec = self.ecodes
        try:
            if action.kind == "click":
                x, y, w, h = rect
                px, py = x + min(w - 1, int(action.x * w)), y + min(h - 1, int(action.y * h))
                subprocess.run(["hyprctl", "dispatch", "movecursor", f"{px} {py}"],
                               check=True, capture_output=True, timeout=2)
                self.check(state)
                self.held.add(ec.BTN_LEFT)
                self.device.write(ec.EV_KEY, ec.BTN_LEFT, 1)
            elif action.kind == "key":
                code = self.keys[action.key]
                self.held.add(code)
                self.device.write(ec.EV_KEY, code, 1)
            elif action.kind == "move":
                self.device.write(ec.EV_REL, ec.REL_X, action.dx)
                self.device.write(ec.EV_REL, ec.REL_Y, action.dy)
            self.device.syn()
            deadline = monotonic() + action.duration_ms / 1000
            while monotonic() < deadline:
                self.check(state)
                sleep(min(0.01, max(0, deadline - monotonic())))
            return True
        finally:
            self.release_all()

    def release_all(self):
        for code in list(self.held):
            self.device.write(self.ecodes.EV_KEY, code, 0)
            self.held.discard(code)
        self.device.syn()

    def close(self):
        try:
            self.release_all()
        finally:
            self.device.close()
