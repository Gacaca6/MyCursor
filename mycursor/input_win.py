"""Win32 cursor and mouse-button injection via SendInput.

Why SendInput and not pyautogui: we need per-frame updates at 30 Hz with
sub-pixel accumulation, real button/wheel events that games and elevated-UI
apps accept, correct behaviour on scaled displays, and multi-monitor
coordinates. pyautogui gives us none of those cheaply.

Movement is delivered as ABSOLUTE coordinates rather than relative deltas.
Relative deltas are reprocessed by Windows pointer acceleration ("enhance
pointer precision"), which would silently fight our own gain curve. We
integrate the tracking delta into a float position ourselves and place the
cursor exactly where we computed, so the feel of the pointer is entirely
determined by config, not by a Windows setting we cannot see.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Literal

Button = Literal["left", "right", "middle"]

# --- DPI awareness ------------------------------------------------------
# Must be set before any screen metric is read. Without it a scaled display
# reports virtualised pixels and the cursor consistently lands short of the
# screen edges.
_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def set_dpi_awareness() -> None:
    user32 = ctypes.windll.user32
    for attempt in (
        lambda: user32.SetProcessDpiAwarenessContext(_PER_MONITOR_AWARE_V2),
        lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
        lambda: user32.SetProcessDPIAware(),
    ):
        try:
            attempt()
            return
        except (AttributeError, OSError):
            continue


# --- structures ---------------------------------------------------------
if ctypes.sizeof(ctypes.c_void_p) == 8:
    ULONG_PTR = ctypes.c_ulonglong
else:
    ULONG_PTR = ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


INPUT_MOUSE = 0

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

WHEEL_DELTA = 120

_DOWN = {
    "left": MOUSEEVENTF_LEFTDOWN,
    "right": MOUSEEVENTF_RIGHTDOWN,
    "middle": MOUSEEVENTF_MIDDLEDOWN,
}
_UP = {
    "left": MOUSEEVENTF_LEFTUP,
    "right": MOUSEEVENTF_RIGHTUP,
    "middle": MOUSEEVENTF_MIDDLEUP,
}

# SM_* indices for the bounding box of all monitors.
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

_user32 = ctypes.windll.user32
_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
_user32.GetSystemMetrics.restype = ctypes.c_int


def _send(*flags_and_data: tuple[int, int]) -> None:
    """Send one or more mouse events in a single atomic SendInput call."""
    events = (INPUT * len(flags_and_data))()
    for i, (flags, data) in enumerate(flags_and_data):
        events[i].type = INPUT_MOUSE
        events[i].mi = MOUSEINPUT(0, 0, data, flags, 0, 0)
    _user32.SendInput(len(events), events, ctypes.sizeof(INPUT))


def work_area() -> tuple[int, int, int, int]:
    """The primary monitor minus the taskbar, as (x, y, width, height).

    GetSystemMetrics reports the full screen, which puts a "bottom corner"
    window underneath the taskbar. SPI_GETWORKAREA is the rectangle apps are
    actually meant to use.
    """
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    rect = RECT()
    SPI_GETWORKAREA = 0x0030
    if not _user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        # Fall back to the whole screen; a slightly low window beats no window.
        return (0, 0, _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1))
    return (
        rect.left,
        rect.top,
        rect.right - rect.left,
        rect.bottom - rect.top,
    )


def find_window(title: str) -> int:
    """HWND of a top-level window by exact title, or 0."""
    return _user32.FindWindowW(None, title) or 0


def outer_size(hwnd: int) -> tuple[int, int]:
    """Full window size including borders and title bar.

    A window is always bigger than the image inside it, so placing by the
    requested client size alone leaves the frame hanging off the screen.
    """
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    rect = RECT()
    if not hwnd or not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (0, 0)
    return (rect.right - rect.left, rect.bottom - rect.top)


def move_window(hwnd: int, x: int, y: int) -> bool:
    """Reposition without resizing or changing z-order."""
    if not hwnd:
        return False
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    return bool(
        _user32.SetWindowPos(
            hwnd, 0, int(x), int(y), 0, 0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
        )
    )


class MouseDriver:
    """Places the cursor and injects buttons across the whole virtual desktop."""

    def __init__(self) -> None:
        set_dpi_awareness()
        self.refresh_geometry()
        self._held: set[Button] = set()

    def refresh_geometry(self) -> None:
        """Re-read monitor layout. Call after a display change."""
        g = _user32.GetSystemMetrics
        self.origin_x = g(_SM_XVIRTUALSCREEN)
        self.origin_y = g(_SM_YVIRTUALSCREEN)
        self.width = max(g(_SM_CXVIRTUALSCREEN), 1)
        self.height = max(g(_SM_CYVIRTUALSCREEN), 1)

    # --- position ------------------------------------------------------
    def get_pos(self) -> tuple[int, int]:
        pt = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def clamp(self, x: float, y: float) -> tuple[float, float]:
        x = min(max(x, self.origin_x), self.origin_x + self.width - 1)
        y = min(max(y, self.origin_y), self.origin_y + self.height - 1)
        return x, y

    def move_to(self, x: float, y: float) -> None:
        """Move to an absolute virtual-desktop pixel coordinate."""
        x, y = self.clamp(x, y)
        # SendInput's absolute space is 0..65535 spanning the virtual desktop.
        nx = int(round((x - self.origin_x) * 65535.0 / max(self.width - 1, 1)))
        ny = int(round((y - self.origin_y) * 65535.0 / max(self.height - 1, 1)))
        events = (INPUT * 1)()
        events[0].type = INPUT_MOUSE
        events[0].mi = MOUSEINPUT(
            nx,
            ny,
            0,
            MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
            0,
            0,
        )
        _user32.SendInput(1, events, ctypes.sizeof(INPUT))

    # --- buttons -------------------------------------------------------
    def press(self, button: Button = "left") -> None:
        if button in self._held:
            return
        self._held.add(button)
        _send((_DOWN[button], 0))

    def release(self, button: Button = "left") -> None:
        if button not in self._held:
            return
        self._held.discard(button)
        _send((_UP[button], 0))

    def click(self, button: Button = "left") -> None:
        # Down and up in one call so no tracking frame can slip between them.
        _send((_DOWN[button], 0), (_UP[button], 0))

    def double_click(self, button: Button = "left") -> None:
        _send(
            (_DOWN[button], 0),
            (_UP[button], 0),
            (_DOWN[button], 0),
            (_UP[button], 0),
        )

    def is_held(self, button: Button = "left") -> bool:
        return button in self._held

    def release_all(self) -> None:
        for button in list(self._held):
            self.release(button)

    # --- wheel ---------------------------------------------------------
    def scroll(self, notches: float) -> None:
        """Positive scrolls up (content down), matching a physical wheel."""
        delta = int(round(notches * WHEEL_DELTA))
        if delta:
            _send((MOUSEEVENTF_WHEEL, delta & 0xFFFFFFFF))

    def hscroll(self, notches: float) -> None:
        delta = int(round(notches * WHEEL_DELTA))
        if delta:
            _send((MOUSEEVENTF_HWHEEL, delta & 0xFFFFFFFF))
