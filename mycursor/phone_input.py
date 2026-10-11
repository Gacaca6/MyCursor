"""Keyboard input and relative touchpad motion, without camera dependencies."""
from __future__ import annotations

import ctypes
from .input_win import MouseDriver, INPUT, KEYBDINPUT, _user32

KEYS = {
    'enter': 0x0D, 'tab': 0x09, 'backspace': 0x08, 'escape': 0x1B,
    'delete': 0x2E, 'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
    'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
    'space': 0x20, 'f5': 0x74, 'volumeup': 0xAF, 'volumedown': 0xAE,
    'mute': 0xAD, 'playpause': 0xB3,
    'copy': (0x11, 0x43), 'paste': (0x11, 0x56), 'undo': (0x11, 0x5A),
    'selectall': (0x11, 0x41), 'switchwindow': (0x12, 0x09),
    'desktop': (0x5B, 0x44), 'start': 0x5B,
}


def send_keys(items: list[tuple[int, int, int]]) -> None:
    events = (INPUT * len(items))()
    for event, (vk, scan, flags) in zip(events, items):
        event.type = 1
        event.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    if _user32.SendInput(len(events), events, ctypes.sizeof(INPUT)) != len(events):
        raise OSError('Windows blocked input. Elevated apps and UAC need a physical keyboard.')


class PhoneDriver(MouseDriver):
    def __init__(self):
        super().__init__()
        self.x, self.y = self.get_pos()

    def move(self, dx: float, dy: float) -> None:
        # Follow an external mouse or keyboard cursor adjustment, but retain
        # fractional pixels when our own rounded position has not changed.
        actual = self.get_pos()
        if abs(actual[0] - self.x) > 2 or abs(actual[1] - self.y) > 2:
            self.x, self.y = actual
        self.refresh_geometry()
        self.x, self.y = self.clamp(self.x + dx, self.y + dy)
        self.move_to(self.x, self.y)

    def key(self, name: str) -> None:
        keys = KEYS[name]
        if isinstance(keys, int):
            keys = (keys,)
        send_keys([(k, 0, 0) for k in keys] + [(k, 0, 2) for k in reversed(keys)])

    def text(self, value: str) -> None:
        # UTF-16 code units support accented text and emoji without changing
        # the user's keyboard layout or clipboard.
        units = value.encode('utf-16-le')
        batch = []
        for i in range(0, len(units), 2):
            unit = int.from_bytes(units[i:i + 2], 'little')
            if unit in (10, 9):
                vk = 0x0D if unit == 10 else 0x09
                batch.extend([(vk, 0, 0), (vk, 0, 2)])
            elif unit != 13:
                batch.extend([(0, unit, 4), (0, unit, 6)])
            if len(batch) >= 128:
                send_keys(batch)
                batch = []
        if batch:
            send_keys(batch)
