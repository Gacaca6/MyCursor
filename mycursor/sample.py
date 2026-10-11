"""The contract between a tracker and the pointer engine.

Trackers do one job: look at a frame and report where the cursor anchor is,
plus what the user appears to be asking for. They never touch the mouse. The
engine owns all pointer maths, so both modes share exactly one gain curve,
one filter and one click-freeze implementation, and behave identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Sample:
    """One frame of tracker output, in normalised frame coordinates."""

    ok: bool = False
    """True when a hand/face was found and the anchor below is meaningful."""

    ax: float = 0.0
    ay: float = 0.0
    """Cursor anchor, 0..1 across the frame. Origin top-left, already mirrored."""

    parked: bool = False
    """User has asked the pointer to hold still (open palm, or tracking lost)."""

    left_down: bool = False
    """Left button should be held this frame. Engine turns changes into
    press/release, so a sustained true becomes a drag and a brief one a click."""

    right_fire: bool = False
    middle_fire: bool = False
    """One-shot click requests, already debounced by the tracker."""

    scroll: float = 0.0
    """Wheel notches to emit this frame."""

    click_disturbance: bool = False
    """The gesture being performed physically moves the anchor. The engine
    freezes movement while this is set, so the cursor does not lurch away
    from the target at the instant of the click."""

    debug: dict[str, Any] = field(default_factory=dict)
    """Values worth drawing on the preview window while tuning."""


class Tracker:
    """Interface implemented by the hand and head trackers."""

    name = "tracker"

    def process(self, rgb, timestamp_ms: int) -> Sample:  # pragma: no cover
        raise NotImplementedError

    def reset(self) -> None:
        """Forget gesture state, e.g. after the pointer is disabled."""

    def close(self) -> None:
        """Release the underlying model."""
