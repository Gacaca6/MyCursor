"""User-tunable settings, persisted as JSON next to the package.

Everything that affects feel lives here rather than in the tracking code,
because getting a camera pointer to feel right is entirely a tuning exercise
and you will want to change these numbers many times without touching logic.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "settings.json"


@dataclass
class CameraConfig:
    index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30
    # The camera sees you mirrored. Flipping makes movement feel direct:
    # move your hand right, the cursor goes right.
    mirror: bool = True


@dataclass
class PointerConfig:
    """Shared by both tracking modes."""

    # Gain curve, used by "relative" control only. Speed is in normalised
    # frame units per second.
    #
    # The deadzone is the most dangerous number here. Landmark noise is
    # high-frequency: small per frame but *fast*, faster than slow deliberate
    # movement. So noise and intent overlap in the speed domain and cannot be
    # cleanly separated by a speed threshold. An earlier version set this to
    # 0.5, which did kill all visible shake -- and also made the pointer
    # impossible to nudge, because anything slower than a flick produced
    # exactly zero movement. opentrack's own documentation warns about the
    # same trap: excessive deadzone destroys precision.
    #
    # Two changes fixed it. This value is now modest, and accel_gain() ramps
    # continuously out of it rather than stepping from nothing to min_gain,
    # so there is no longer a band where the cursor simply refuses to move.
    # For hand tracking the better answer is "absolute" control, which skips
    # this curve entirely -- see control_mode below.
    deadzone: float = 0.14
    speed_knee: float = 1.1
    min_gain: float = 900.0
    max_gain: float = 4200.0
    accel_exponent: float = 1.6

    # One Euro filter, applied to the raw landmark before gain.
    # Measured: 4.91 px/frame of shake unfiltered, 0.01 px/frame with these.
    filter_min_cutoff: float = 0.4
    filter_beta: float = 0.02
    filter_d_cutoff: float = 1.0

    # Freeze movement briefly around a click. Pinching or opening your jaw
    # physically moves the tracked point, so without this the cursor lurches
    # at the exact instant you are trying to hit something.
    click_freeze_ms: int = 180

    # Keep the pointer this many pixels clear of the desktop edge, so it
    # cannot get stranded off-screen when tracking drops out.
    screen_margin: int = 2

    # How anchor movement becomes cursor movement:
    #   "auto"     - pick per tracking mode: absolute for hand, relative for
    #                head. This is almost always what you want.
    #   "absolute" - anchor position maps straight onto the screen. The right
    #                choice for a hand, which has a real position in space and
    #                plenty of range; every working hand-mouse works this way.
    #                Needs stabilise_px below to stay steady.
    #   "relative" - movement nudges the cursor, mouse-like. The right choice
    #                for a head, whose range is too small to cover a screen.
    #   "velocity" - offset from centre becomes a speed. Hold a small turn and
    #                the cursor keeps going. Implemented but not yet tuned.
    control_mode: str = "auto"

    # --- absolute mode ---------------------------------------------------
    # The active region: the fraction of the frame trimmed off each edge
    # before mapping what is left onto the whole screen. You cannot comfortably
    # reach the corners of the camera's view, and tracking degrades near the
    # frame edge, so a comfortable central rectangle is mapped instead.
    active_margin_x: float = 0.20
    active_margin_y: float = 0.18

    # Position stabiliser, in screen pixels. The cursor ignores any movement
    # of the target smaller than this, and follows only the excess beyond it.
    #
    # This is the key difference from a speed deadzone, and why absolute mode
    # can be both steady and precise: noise and intent overlap in *speed* but
    # not in *position*. Jitter stays within a few pixels; deliberate movement
    # does not. Subtracting the radius rather than gating on it means there is
    # no threshold to cross -- movement fades in smoothly from zero.
    stabilise_px: float = 9.0

    # The clutch, and the answer to "the cursor is bottom-left, the button I
    # want is top-right, and my arm has run out of room".
    #
    # With it off, the mapping is rigidly absolute: the top-right of the box is
    # the top-right of the screen and nowhere else, so a far corner needs your
    # hand in that corner -- exactly where reach is worst and tracking is
    # least reliable.
    #
    # With it on, parking (open palm) and then unparking re-anchors: wherever
    # your hand is when you close it again becomes the reference for wherever
    # the cursor already was. So you sweep, park, bring your arm back to
    # centre, unpark, and sweep again -- the same way you lift a mouse off the
    # pad and put it down again. You can cross any distance in stages without
    # ever reaching the edge of the box.
    clutch: bool = True

    # --- velocity mode ---------------------------------------------------
    velocity_max_px_s: float = 1500.0
    velocity_deadzone: float = 0.05
    velocity_exponent: float = 2.0


@dataclass
class HeadConfig:
    """Head mode: the low-fatigue daily driver."""

    sensitivity_x: float = 1.0
    sensitivity_y: float = 1.15  # vertical head range is smaller, compensate

    # "dwell"  - hover still to click (fully hands-free)
    # "gesture"- jaw-open = left, brow-raise = right
    # "none"   - move only; click some other way
    click_mode: str = "dwell"

    dwell_radius_px: float = 26.0
    dwell_time_ms: int = 700
    dwell_cooldown_ms: int = 600

    jaw_open_threshold: float = 0.40
    brow_raise_threshold: float = 0.45
    gesture_cooldown_ms: int = 450


@dataclass
class HandConfig:
    """Hand mode: gestures, at the cost of arm fatigue."""

    # Pinch distance between thumb tip and finger tip, normalised by hand
    # size so it works the same near or far from the camera. Two values for
    # hysteresis: engage below the first, release above the second.
    pinch_on: float = 0.34
    pinch_off: float = 0.48

    # Hold a pinch this long and it becomes a drag instead of a click.
    drag_hold_ms: int = 320

    scroll_sensitivity: float = 14.0
    scroll_deadzone: float = 0.015

    # How much farther than its middle joint a fingertip must sit before the
    # finger counts as extended, as a fraction. A bare comparison (margin 0)
    # is what stopped scrolling working: a half-curled ring or pinky finger
    # would flicker to "extended", which satisfied the open-palm park gesture
    # and starved the scroll pose of ever matching. Requiring a clear margin
    # makes "extended" a decisive state instead of a coin toss.
    extend_margin: float = 0.12

    # The pinky is the least reliably tracked finger on the hand, so by
    # default the scroll pose does not care what it is doing: index and middle
    # up with the ring finger down is enough. Set true to demand a precise
    # two-finger pose.
    scroll_requires_pinky_down: bool = False

    # An open palm parks the pointer, so you can lower your arm and rest
    # without the cursor flying into a corner.
    park_on_open_palm: bool = True

    # Which hand to track when both are visible.
    preferred_hand: str = "any"  # "any" | "Left" | "Right"

    # "palm" anchors on the wrist/knuckle midpoint, which barely moves when
    # your fingers pinch, so clicks do not drag the cursor off target.
    # "index_tip" feels more like pointing but drifts on every click.
    cursor_anchor: str = "palm"


@dataclass
class PreviewConfig:
    """The on-screen monitor window.

    Deliberately small and cornered rather than a big always-on-top video
    feed. On a 1366x768 screen a full preview covers a third of your desktop,
    and you only ever need three things from it: is my hand inside the active
    box, what pose does it think I am making, and is the pointer on.
    """

    width: int = 360  # height follows the camera's aspect ratio
    corner: str = "bottom-right"  # top-left | top-right | bottom-left | bottom-right
    margin_px: int = 16
    topmost: bool = True


@dataclass
class HotkeyConfig:
    """Virtual-key names, resolved in hotkeys.py."""

    # Not ctrl+alt+space: the Claude desktop app registers that globally, and
    # a chord another process already owns simply never arrives. Verified with
    # tools/check_hotkeys.py, which tries to claim each candidate for real.
    # ctrl+alt+z is a comfortable one-handed reach and rarely contested.
    toggle_enable: str = "ctrl+alt+z"
    switch_mode: str = "ctrl+alt+m"
    recenter: str = "ctrl+alt+c"
    quit: str = "ctrl+alt+q"
    left_click: str = "ctrl+alt+j"  # keyboard fallback while you tune
    legend: str = "ctrl+alt+g"  # show the gesture trainer card


# Bumped whenever a stored setting changes meaning or its default becomes
# wrong rather than merely different. _migrate() below resets exactly those
# keys so an old settings.json cannot silently pin you to old behaviour.
CONFIG_VERSION = 3

# Keys retired or redefined at each version, cleared on upgrade past it.
_STALE_ON_UPGRADE = {
    2: [
        # v1 shipped control_mode="relative" for everything. Relative is wrong
        # for a hand, which has a real position and range to map from.
        ("pointer", "control_mode"),
        # v1's tuner produced deadzone=0.5, which removed all visible shake
        # and also made the pointer impossible to nudge: anything slower than
        # a flick produced exactly zero movement.
        ("pointer", "deadzone"),
    ],
    3: [
        # v2 defaulted the wake hotkey to ctrl+alt+space, which the Claude
        # desktop app claims globally, so the hotkey never fired. Changing the
        # code default alone would not have helped anyone with it already
        # saved -- which is the whole reason this migration table exists.
        ("hotkeys", "toggle_enable"),
    ],
}


@dataclass
class Config:
    config_version: int = CONFIG_VERSION
    mode: str = "head"  # "head" | "hand"
    start_enabled: bool = False  # require an explicit hotkey before moving
    show_preview: bool = True

    # Practice mode. Everything runs -- camera, tracking, preview, gesture
    # detection -- but no mouse event is ever emitted. Use it to learn the
    # gestures or tune the active region without the cursor running away,
    # and to test changes safely.
    move_pointer: bool = True

    # How often to check for the wake hotkey while idle. The idle loop runs no
    # camera and no inference, so this is the app's entire cost when off.
    idle_poll_ms: int = 40

    # Unload the tracking models when idle too. Frees a couple of hundred MB
    # at the price of a ~1s pause on every activation. Worth enabling only on
    # a memory-starved machine; the camera is released either way, which is
    # what matters for letting other apps use the webcam.
    release_models_when_idle: bool = False
    camera: CameraConfig = field(default_factory=CameraConfig)
    pointer: PointerConfig = field(default_factory=PointerConfig)
    head: HeadConfig = field(default_factory=HeadConfig)
    hand: HandConfig = field(default_factory=HandConfig)
    preview: PreviewConfig = field(default_factory=PreviewConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)

    # --- persistence ---------------------------------------------------
    def save(self, path: Path | None = None) -> Path:
        path = path or CONFIG_PATH
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or CONFIG_PATH
        if not path.exists():
            cfg = cls()
            cfg.save(path)
            return cfg
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A corrupt settings file must not stop you from getting a cursor.
            return cls()
        raw, notes = _migrate(raw)
        config = _merge(cls, raw)
        config.config_version = CONFIG_VERSION
        if notes:
            config.save(path)
            for note in notes:
                print(f"  [settings migrated] {note}")
        return config


def _merge(dc_type: type, raw: Any) -> Any:
    """Overlay JSON onto fresh defaults, recursing into nested sections.

    Start from a default instance and only overwrite what the file actually
    provides. That is what lets an old settings.json keep working when a new
    option is added, and lets you delete a key to get its default back.
    """
    instance = dc_type()
    if not isinstance(raw, dict):
        return instance
    for f in fields(dc_type):
        if f.name not in raw:
            continue
        current = getattr(instance, f.name)
        if is_dataclass(current):
            setattr(instance, f.name, _merge(type(current), raw[f.name]))
        else:
            setattr(instance, f.name, raw[f.name])
    return instance


def _migrate(raw: dict) -> tuple[dict, list[str]]:
    """Drop stored values that a newer version has redefined.

    Merging an old settings.json over new defaults is normally exactly what
    you want -- it is what lets your tuning survive an upgrade. But it also
    means a value whose *default* was wrong keeps being honoured forever. That
    is not hypothetical: v1 stored control_mode="relative" and deadzone=0.5,
    so a fixed build would still load the broken feel and appear unchanged.

    Only the specific keys listed per version are cleared. Everything else,
    including values you measured with the tuner, is kept.
    """
    if not isinstance(raw, dict):
        return raw, []
    stored = raw.get("config_version", 1)
    if not isinstance(stored, int) or stored >= CONFIG_VERSION:
        return raw, []

    notes: list[str] = []
    for version, keys in sorted(_STALE_ON_UPGRADE.items()):
        if stored >= version:
            continue
        for section, key in keys:
            block = raw.get(section)
            if isinstance(block, dict) and key in block:
                notes.append(
                    f"{section}.{key} was {block.pop(key)!r}, reset to the new default"
                )
    raw["config_version"] = CONFIG_VERSION
    return raw, notes
