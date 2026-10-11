"""Find out which global hotkeys are actually free on this machine.

Guessing is unreliable -- Claude, Windows itself, OneDrive, GPU control panels
and IDEs all claim combinations, and a claimed one simply never reaches
MyCursor. RegisterHotKey is the honest test: it fails with
ERROR_HOTKEY_ALREADY_REGISTERED when another process already owns a chord, so
we try to claim each candidate and immediately release it.

One limitation worth knowing: this only detects apps that reserve hotkeys the
documented way. Anything using a low-level keyboard hook is invisible to it, so
a combo reported free can still be swallowed. If a hotkey looks free here and
still does nothing, that is the reason -- pick another.

    .\\.venv\\Scripts\\python.exe tools\\check_hotkeys.py
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mycursor.config import Config
from mycursor.hotkeys import BadHotkey, parse

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Modifier flags for RegisterHotKey (different values to the VK codes).
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_VK_TO_MOD = {0x12: MOD_ALT, 0x11: MOD_CONTROL, 0x10: MOD_SHIFT, 0x5B: MOD_WIN}

ERROR_HOTKEY_ALREADY_REGISTERED = 1409

# Candidates that avoid the usual suspects. Deliberately no F-keys: on this
# laptop the F row doubles as media keys via Fn, which makes them unreliable
# as hotkeys depending on Fn-lock state.
CANDIDATES = [
    "ctrl+alt+space",
    "ctrl+alt+home",
    "ctrl+alt+end",
    "ctrl+alt+insert",
    "ctrl+alt+pagedown",
    "ctrl+alt+z",
    "ctrl+alt+g",
    "ctrl+alt+h",
    "ctrl+alt+k",
    "ctrl+alt+enter",
    "ctrl+shift+space",
    "ctrl+shift+z",
    "alt+shift+space",
    "ctrl+alt+numlock",
]


def is_free(spec: str) -> tuple[bool, str]:
    """Try to claim a chord, then release it. Returns (free, reason)."""
    try:
        mods, main = parse(spec)
    except BadHotkey as exc:
        return False, f"unparseable: {exc}"

    flags = MOD_NOREPEAT
    for vk in mods:
        flags |= _VK_TO_MOD.get(vk, 0)

    hotkey_id = 0xBEEF
    kernel32.SetLastError(0)
    if user32.RegisterHotKey(None, hotkey_id, wintypes.UINT(flags), wintypes.UINT(main)):
        user32.UnregisterHotKey(None, hotkey_id)
        return True, "free"

    err = kernel32.GetLastError()
    if err == ERROR_HOTKEY_ALREADY_REGISTERED:
        return False, "TAKEN by another app"
    return False, f"refused (error {err})"


def main() -> int:
    cfg = Config.load()
    configured = {
        "toggle (wake/sleep)": cfg.hotkeys.toggle_enable,
        "switch mode": cfg.hotkeys.switch_mode,
        "recentre": cfg.hotkeys.recenter,
        "left click": cfg.hotkeys.left_click,
        "quit": cfg.hotkeys.quit,
    }

    print("Your configured hotkeys")
    print("-" * 52)
    clashes = []
    for label, spec in configured.items():
        free, reason = is_free(spec)
        mark = "ok" if free else "CLASH"
        print(f"  {label:22} {spec:20} {mark}")
        if not free:
            clashes.append((label, spec, reason))

    if clashes:
        print()
        for label, spec, reason in clashes:
            print(f"  ! {spec} ({label}): {reason}")

    print()
    print("Candidates")
    print("-" * 52)
    free_ones = []
    for spec in CANDIDATES:
        free, reason = is_free(spec)
        if free:
            free_ones.append(spec)
            print(f"  {spec:22} free")
        else:
            print(f"  {spec:22} {reason}")

    print()
    if free_ones:
        print("Suggested settings.json hotkeys block:")
        print()
        picks = [s for s in free_ones if s not in configured.values()]
        wake = picks[0] if picks else free_ones[0]
        print('  "hotkeys": {')
        print(f'    "toggle_enable": "{wake}",')
        for label, key in (
            ("switch_mode", cfg.hotkeys.switch_mode),
            ("recenter", cfg.hotkeys.recenter),
            ("left_click", cfg.hotkeys.left_click),
            ("quit", cfg.hotkeys.quit),
        ):
            print(f'    "{label}": "{key}",')
        print("  }")
    else:
        print("Nothing in the candidate list is free. Add your own ideas to")
        print("CANDIDATES in this file and re-run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
