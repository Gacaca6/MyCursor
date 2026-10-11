"""Global hotkeys by polling GetAsyncKeyState.

RegisterHotKey would be the textbook choice, but it needs a window and a
message pump, which means another thread fighting the capture loop. We are
already waking up 30 times a second to read a camera frame, so sampling the
keyboard on the same tick is simpler, has no threading to get wrong, and is
plenty responsive for a chord.

These work no matter which window has focus, which matters because the whole
point is being able to switch the pointer off when it misbehaves.
"""

from __future__ import annotations

import ctypes

_user32 = ctypes.windll.user32

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B

_MODIFIERS = {
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "alt": VK_MENU,
    "shift": VK_SHIFT,
    "win": VK_LWIN,
}

_NAMED_KEYS = {
    "space": 0x20,
    "esc": 0x1B,
    "escape": 0x1B,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "pause": 0x13,
}
for _i in range(1, 25):
    _NAMED_KEYS[f"f{_i}"] = 0x6F + _i


class BadHotkey(ValueError):
    pass


def parse(spec: str) -> tuple[frozenset[int], int]:
    """Turn "ctrl+alt+space" into ({VK_CONTROL, VK_MENU}, 0x20)."""
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise BadHotkey(f"empty hotkey: {spec!r}")

    mods: set[int] = set()
    main: int | None = None
    for part in parts:
        if part in _MODIFIERS:
            mods.add(_MODIFIERS[part])
        elif part in _NAMED_KEYS:
            main = _NAMED_KEYS[part]
        elif len(part) == 1 and (part.isalpha() or part.isdigit()):
            main = ord(part.upper())
        else:
            raise BadHotkey(f"unrecognised key {part!r} in hotkey {spec!r}")

    if main is None:
        raise BadHotkey(f"hotkey {spec!r} has modifiers but no main key")
    return frozenset(mods), main


def _down(vk: int) -> bool:
    # The high bit of the return value is the physical down state. The low
    # bit is a "pressed since last call" toggle we deliberately ignore,
    # because several callers may poll the same key on one tick.
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


class Hotkeys:
    """Edge-triggered global chords, sampled once per frame."""

    def __init__(self) -> None:
        self._bindings: dict[str, tuple[frozenset[int], int]] = {}
        self._was_down: dict[str, bool] = {}
        self.errors: list[str] = []

    def bind(self, name: str, spec: str) -> None:
        """Register a chord. A bad spec is recorded, not raised: one typo in
        settings.json must not stop the pointer from starting."""
        if not spec:
            return
        try:
            self._bindings[name] = parse(spec)
        except BadHotkey as exc:
            self.errors.append(str(exc))
            return
        self._was_down[name] = False

    def poll(self) -> set[str]:
        """Return the names of chords that became pressed since the last call."""
        fired: set[str] = set()
        for name, (mods, main) in self._bindings.items():
            held = _down(main) and all(_down(m) for m in mods)
            if held and not self._was_down[name]:
                fired.add(name)
            self._was_down[name] = held
        return fired

    def is_held(self, name: str) -> bool:
        binding = self._bindings.get(name)
        if binding is None:
            return False
        mods, main = binding
        return _down(main) and all(_down(m) for m in mods)
