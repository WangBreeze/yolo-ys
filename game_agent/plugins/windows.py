"""Windows client-area capture and bounded SendInput; imported only when selected.

API v1: BGR pixels and normalized client coordinates match the other adapters.
The ctypes layouts use Windows' fixed-width integers, including on Linux tests.
"""

import ctypes as ct
import sys
from contextlib import contextmanager
from time import monotonic, monotonic_ns, sleep

from ..contracts import Frame
from .base import Plugin


class MouseInput(ct.Structure):
    _fields_ = [("dx", ct.c_int32), ("dy", ct.c_int32), ("mouseData", ct.c_uint32),
                ("dwFlags", ct.c_uint32), ("time", ct.c_uint32), ("dwExtraInfo", ct.c_size_t)]


class KeyboardInput(ct.Structure):
    _fields_ = [("wVk", ct.c_uint16), ("wScan", ct.c_uint16), ("dwFlags", ct.c_uint32),
                ("time", ct.c_uint32), ("dwExtraInfo", ct.c_size_t)]


class HardwareInput(ct.Structure):
    _fields_ = [("uMsg", ct.c_uint32), ("wParamL", ct.c_uint16), ("wParamH", ct.c_uint16)]


class InputUnion(ct.Union):
    _fields_ = [("mi", MouseInput), ("ki", KeyboardInput), ("hi", HardwareInput)]


class Input(ct.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", ct.c_uint32), ("value", InputUnion)]


class Rect(ct.Structure):
    _fields_ = [(name, ct.c_int32) for name in ("left", "top", "right", "bottom")]


class Point(ct.Structure):
    _fields_ = [("x", ct.c_int32), ("y", ct.c_int32)]


def virtual_key(name):
    named = {"ESC": 0x1B, "ESCAPE": 0x1B, "SPACE": 0x20, "ENTER": 0x0D,
             "TAB": 0x09, "SHIFT": 0xA0, "CTRL": 0xA2, "ALT": 0xA4,
             "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
             "BACKSPACE": 0x08, "DELETE": 0x2E}
    name = name.upper()
    if len(name) == 1 and name in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        return ord(name)
    if name.startswith("F") and name[1:].isdigit() and 1 <= int(name[1:]) <= 12:
        return 0x6F + int(name[1:])
    if name not in named:
        raise ValueError(f"unsupported Windows key: {name}")
    return named[name]


def absolute_position(x, y, desktop):
    left, top, width, height = desktop
    if width <= 1 or height <= 1 or not (left <= x < left + width and top <= y < top + height):
        raise ValueError("click is outside the virtual desktop")
    return round((x - left) * 65535 / (width - 1)), round((y - top) * 65535 / (height - 1))


def check_window(window, options, expected_id=None):
    if not options.get("window_class") and not options.get("window_title"):
        raise ValueError("configure an exact window_class or window_title")
    if not window.get("visible") or window.get("minimized"):
        raise ValueError("target window is hidden or minimized")
    for option, field in (("window_class", "class"), ("window_title", "title")):
        if options.get(option) and window.get(field) != options[option]:
            raise ValueError("target window is not in the foreground")
    if expected_id and window["id"] != expected_id:
        raise ValueError("foreground window identity changed")
    rect = window["rect"]
    if len(rect) != 4 or any(type(v) is not int for v in rect) or min(rect[2:]) <= 0:
        raise ValueError("invalid client rectangle")
    return rect


class Win32Desktop:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Windows desktop plugins require Windows 10/11; use Linux offline tools here")
        self.user32 = ct.WinDLL("user32", use_last_error=True)
        signatures = {
            "GetForegroundWindow": ([], ct.c_void_p),
            "GetWindowTextLengthW": ([ct.c_void_p], ct.c_int),
            "GetWindowTextW": ([ct.c_void_p, ct.c_wchar_p, ct.c_int], ct.c_int),
            "GetClassNameW": ([ct.c_void_p, ct.c_wchar_p, ct.c_int], ct.c_int),
            "GetWindowThreadProcessId": ([ct.c_void_p, ct.POINTER(ct.c_uint32)], ct.c_uint32),
            "GetClientRect": ([ct.c_void_p, ct.POINTER(Rect)], ct.c_int),
            "ClientToScreen": ([ct.c_void_p, ct.POINTER(Point)], ct.c_int),
            "IsWindowVisible": ([ct.c_void_p], ct.c_int),
            "IsIconic": ([ct.c_void_p], ct.c_int),
            "GetSystemMetrics": ([ct.c_int], ct.c_int),
            "MapVirtualKeyW": ([ct.c_uint32, ct.c_uint32], ct.c_uint32),
            "GetAsyncKeyState": ([ct.c_int], ct.c_int16),
            "SendInput": ([ct.c_uint32, ct.POINTER(Input), ct.c_int], ct.c_uint32),
            "SetThreadDpiAwarenessContext": ([ct.c_void_p], ct.c_void_p),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.user32, name)
            function.argtypes, function.restype = args, result

    @contextmanager
    def dpi(self):
        # Restore the thread context after each operation; don't alter global settings.
        old = self.user32.SetThreadDpiAwarenessContext(ct.c_void_p(-4))
        if not old:
            raise OSError("per-monitor DPI awareness could not be enabled")
        try:
            yield
        finally:
            self.user32.SetThreadDpiAwarenessContext(old)

    def foreground(self):
        with self.dpi():
            u = self.user32
            handle = u.GetForegroundWindow()
            if not handle:
                raise ValueError("no foreground window")
            title = ct.create_unicode_buffer(u.GetWindowTextLengthW(handle) + 1)
            name = ct.create_unicode_buffer(256)
            u.GetWindowTextW(handle, title, len(title))
            u.GetClassNameW(handle, name, len(name))
            pid, rect, origin = ct.c_uint32(), Rect(), Point()
            if not u.GetWindowThreadProcessId(handle, ct.byref(pid)):
                raise OSError("cannot read window process")
            if not u.GetClientRect(handle, ct.byref(rect)) or not u.ClientToScreen(handle, ct.byref(origin)):
                raise OSError("cannot read window client geometry")
            result = {"id": f"{handle:x}:{pid.value}", "title": title.value, "class": name.value,
                      "rect": [origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top],
                      "visible": bool(u.IsWindowVisible(handle)), "minimized": bool(u.IsIconic(handle))}
            if handle != u.GetForegroundWindow():
                raise ValueError("foreground changed during window query")
            return result

    def _send(self, value):
        if self.user32.SendInput(1, ct.byref(value), ct.sizeof(Input)) != 1:
            raise OSError("SendInput was rejected; check foreground window and matching integrity levels")

    def is_down(self, key):
        return bool(self.user32.GetAsyncKeyState(key) & 0x8000)

    def key(self, key, down):
        scan = self.user32.MapVirtualKeyW(key, 4)  # MAPVK_VK_TO_VSC_EX
        if not scan:
            raise ValueError("key has no scan-code mapping")
        flags = 0x0008 | (0 if down else 0x0002) | (0x0001 if scan & 0xFF00 else 0)
        value = Input(type=1)
        value.ki = KeyboardInput(0, scan & 0xFF, flags, 0, 0)
        self._send(value)

    def button(self, down):
        value = Input(type=0)
        value.mi = MouseInput(0, 0, 0, 0x0002 if down else 0x0004, 0, 0)
        self._send(value)

    def move(self, x, y, absolute=False):
        with self.dpi():
            flags = 0x0001
            if absolute:
                desktop = [self.user32.GetSystemMetrics(i) for i in (76, 77, 78, 79)]
                x, y = absolute_position(x, y, desktop)
                flags |= 0x8000 | 0x4000  # ABSOLUTE + VIRTUALDESK, including negative monitor origins
            value = Input(type=0)
            value.mi = MouseInput(x, y, 0, flags, 0, 0)
            self._send(value)


def create_grabber():
    from mss import MSS
    return MSS()


class WindowsCapture(Plugin):
    ROLE = "capture"
    mode = "live"

    def __init__(self, context, options):
        super().__init__(context, options)
        if not options.get("window_class") and not options.get("window_title"):
            raise ValueError("configure an exact window_class or window_title")
        self.desktop = Win32Desktop()
        with self.desktop.dpi():
            self.grabber = create_grabber()
        self.sequence = 0

    def capture(self):
        import numpy as np
        started = monotonic_ns()
        window = self.desktop.foreground()
        x, y, w, h = check_window(window, self.options)
        with self.desktop.dpi():
            shot = self.grabber.grab({"left": x, "top": y, "width": w, "height": h})
            pixels = np.asarray(shot, dtype=np.uint8)[:, :, :3].copy()
        if check_window(self.desktop.foreground(), self.options, window["id"]) != [x, y, w, h]:
            raise ValueError("window moved during capture")
        if pixels.shape != (h, w, 3):
            raise ValueError("capture dimensions differ from the physical client rectangle")
        self.sequence += 1
        return Frame(self.sequence, started, w, h, pixels,
                     {"__window_rect": [x, y, w, h]}, True, window["id"])

    def close(self):
        self.grabber.close()


class WindowsController(Plugin):
    ROLE = "controller"
    mode = "live"

    def __init__(self, context, options):
        super().__init__(context, options)
        if context.mode != "live" or not context.services.get("live_enabled"):
            raise ValueError("Windows input requires live mode and --live")
        if not options.get("window_class") and not options.get("window_title"):
            raise ValueError("configure an exact window_class or window_title")
        self.keys = {name: virtual_key(name) for name in context.config["runtime"]["allowed_keys"]}
        self.desktop = Win32Desktop()
        self.held = set()

    def check(self, state):
        settings = self.context.config["runtime"]
        if self.context.output_path(settings["stop_file"]).exists():
            raise ValueError("stop file present")
        if self.desktop.is_down(0x7B):  # F12 is an independent emergency stop, never an agent key.
            raise ValueError("F12 emergency stop")
        if not state.focused or not state.window_id:
            raise ValueError("observation has no focused target window")
        rect = check_window(self.desktop.foreground(), self.options, state.window_id)
        if rect != state.facts.get("__window_rect"):
            raise ValueError("window geometry changed since observation")
        age = (monotonic_ns() - state.captured_ns) / 1e6
        if not 0 <= age <= settings["max_frame_age_ms"]:
            raise ValueError("observation expired before/during input")
        return rect

    def execute(self, action, state):
        if action.duration_ms > self.context.config["runtime"]["max_action_ms"]:
            raise ValueError("action exceeds profile duration limit")
        if action.kind == "key" and (action.key not in self.keys or self.keys[action.key] == 0x7B):
            raise ValueError("key is not allowed (F12 is reserved for stopping)")
        rect = self.check(state)
        try:
            if action.kind == "click":
                x, y, w, h = rect
                self.desktop.move(x + min(w - 1, int(action.x * w)),
                                  y + min(h - 1, int(action.y * h)), absolute=True)
                self.check(state)
                if self.desktop.is_down(0x01):
                    raise ValueError("left mouse button is already held by the user")
                self.held.add(("button", 0x01))
                self.desktop.button(True)
            elif action.kind == "key":
                key = self.keys[action.key]
                if self.desktop.is_down(key):
                    raise ValueError("requested key is already held by the user")
                self.held.add(("key", key))
                self.desktop.key(key, True)
            elif action.kind == "move":
                self.desktop.move(action.dx, action.dy)
            deadline = monotonic() + action.duration_ms / 1000
            while monotonic() < deadline:
                self.check(state)
                sleep(min(0.01, max(0, deadline - monotonic())))
            return action.kind != "wait"
        finally:
            self.release_all()

    def release_all(self):
        errors = []
        for kind, key in list(self.held):
            try:
                self.desktop.key(key, False) if kind == "key" else self.desktop.button(False)
                self.held.discard((kind, key))
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise OSError("could not release all agent inputs") from errors[0]

    def close(self):
        self.release_all()
