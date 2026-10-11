"""Hand mode: gesture pointing with MediaPipe Hand Landmarker.

Design note on the cursor anchor. The obvious choice is the index fingertip,
because pointing with your finger is what feels natural. It is also the worst
choice available: the fingertip is exactly what moves when you pinch, so every
click drags the cursor off the thing you were aiming at. We anchor on the palm
centre instead (the midpoint of the wrist and the middle-finger knuckle),
which barely moves when the fingers do. That removes click drift structurally
rather than papering over it with a freeze timer. Set cursor_anchor to
"index_tip" in settings.json if you prefer the classic feel.
"""

from __future__ import annotations

import time

from .config import HandConfig
from .filters import Cooldown, Hysteresis, RisingEdge, dist
from .models import ensure
from .sample import Sample, Tracker

# Landmark indices from the 21-point hand model.
WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20

_EXTENSION_PAIRS = (
    (INDEX_TIP, INDEX_PIP),
    (MIDDLE_TIP, MIDDLE_PIP),
    (RING_TIP, RING_PIP),
    (PINKY_TIP, PINKY_PIP),
)


def _finger_text(extended: tuple[bool, ...]) -> str:
    """Render finger states for the preview, e.g. "I:up M:up R:dn P:dn".

    Worth having on screen: nearly every "gesture X does not work" problem is
    really "the pose you are making is not the pose you think you are making",
    and this shows it directly.
    """
    return " ".join(
        f"{name}:{'up' if state else 'dn'}"
        for name, state in zip("IMRP", extended)
    )


class HandTracker(Tracker):
    name = "hand"

    def __init__(self, cfg: HandConfig, mirror: bool) -> None:
        # Imported lazily so a missing mediapipe install produces one clear
        # message from main() instead of an import error at start-up.
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        self.cfg = cfg
        self.mirror = mirror

        model_path = str(ensure("hand_landmarker.task"))
        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1 if cfg.preferred_hand == "any" else 2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)

        # Pinch gates. Two thresholds each, so fingers hovering near the
        # boundary cannot machine-gun clicks.
        self._left_pinch = Hysteresis(cfg.pinch_on, cfg.pinch_off)
        self._right_pinch = Hysteresis(cfg.pinch_on, cfg.pinch_off)
        self._right_edge = RisingEdge()
        self._right_cooldown = Cooldown(0.35)

        self._pinch_started: float | None = None
        self._dragging = False
        self._last_scroll_y: float | None = None
        self._last_ts = 0

    # --- helpers -------------------------------------------------------
    @staticmethod
    def _hand_scale(lm) -> float:
        """A size reference that does not change as the fingers move.

        Wrist to middle-knuckle stays constant whatever the fingers do, so
        dividing by it makes every gesture threshold behave identically
        whether your hand is close to the camera or far from it.
        """
        return max(
            dist(lm[WRIST].x, lm[WRIST].y, lm[MIDDLE_MCP].x, lm[MIDDLE_MCP].y), 1e-6
        )

    @staticmethod
    def _extended(lm, margin: float = 0.0) -> tuple[bool, ...]:
        """Which of index/middle/ring/pinky are straightened.

        A finger counts as extended when its tip sits farther from the wrist
        than its middle joint does, by at least `margin` as a fraction.

        The margin matters more than it looks. With a bare comparison a
        half-curled ring or pinky finger sits right on the boundary and
        flickers between states frame to frame. Because the open-palm park
        gesture needs all four fingers extended, that flicker was enough to
        keep triggering park and leave the scroll pose never matching. A
        margin turns extension into a decisive state.
        """
        wx, wy = lm[WRIST].x, lm[WRIST].y
        threshold = 1.0 + margin
        return tuple(
            dist(wx, wy, lm[tip].x, lm[tip].y)
            > dist(wx, wy, lm[pip].x, lm[pip].y) * threshold
            for tip, pip in _EXTENSION_PAIRS
        )

    def _pick_hand(self, result) -> int | None:
        if not result.hand_landmarks:
            return None
        want = self.cfg.preferred_hand
        if want == "any":
            return 0
        # Handedness is reported from the camera's point of view, so a
        # mirrored preview flips which label is the user's real hand.
        for i, categories in enumerate(result.handedness):
            if not categories:
                continue
            label = categories[0].category_name
            if self.mirror:
                label = "Left" if label == "Right" else "Right"
            if label == want:
                return i
        return 0

    # --- main ----------------------------------------------------------
    def process(self, rgb, timestamp_ms: int) -> Sample:
        # detect_for_video rejects a non-increasing timestamp, which happens
        # whenever two frames land inside the same millisecond.
        if timestamp_ms <= self._last_ts:
            timestamp_ms = self._last_ts + 1
        self._last_ts = timestamp_ms

        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, timestamp_ms)

        index = self._pick_hand(result)
        if index is None:
            return self._lost()

        lm = result.hand_landmarks[index]
        scale = self._hand_scale(lm)

        if self.cfg.cursor_anchor == "index_tip":
            ax, ay = lm[INDEX_TIP].x, lm[INDEX_TIP].y
        else:
            ax = (lm[WRIST].x + lm[MIDDLE_MCP].x) / 2.0
            ay = (lm[WRIST].y + lm[MIDDLE_MCP].y) / 2.0

        if self.mirror:
            ax = 1.0 - ax

        extended = self._extended(lm, self.cfg.extend_margin)
        index_up, middle_up, ring_up, pinky_up = extended

        sample = Sample(ok=True, ax=ax, ay=ay)

        # --- scroll: index+middle up, ring down -------------------------
        # Checked before park because it is the more specific pose, and
        # because a mis-read finger should fail safe to "not scrolling"
        # rather than silently becoming a park.
        scrolling = index_up and middle_up and not ring_up
        if scrolling and self.cfg.scroll_requires_pinky_down:
            scrolling = not pinky_up
        if scrolling:
            y = lm[INDEX_TIP].y
            if self._last_scroll_y is not None:
                delta = self._last_scroll_y - y  # hand moves up => scroll up
                if abs(delta) > self.cfg.scroll_deadzone:
                    sample.scroll = delta * self.cfg.scroll_sensitivity
            self._last_scroll_y = y
            self._release_everything(sample)
            sample.parked = True  # do not also move the cursor while scrolling
            sample.debug = {
                "gesture": "SCROLL",
                "scroll": round(sample.scroll, 2),
                "fingers": _finger_text(extended),
            }
            return sample
        self._last_scroll_y = None

        # --- park: an open palm means "I am resting my arm" -------------
        if self.cfg.park_on_open_palm and all(extended):
            self._release_everything(sample)
            sample.parked = True
            sample.debug = {
                "gesture": "PARKED (open palm)",
                "fingers": _finger_text(extended),
            }
            return sample

        # --- clicks -----------------------------------------------------
        left_metric = (
            dist(lm[THUMB_TIP].x, lm[THUMB_TIP].y, lm[INDEX_TIP].x, lm[INDEX_TIP].y)
            / scale
        )
        right_metric = (
            dist(lm[THUMB_TIP].x, lm[THUMB_TIP].y, lm[MIDDLE_TIP].x, lm[MIDDLE_TIP].y)
            / scale
        )

        left_pinched = self._left_pinch.update(left_metric)
        right_pinched = self._right_pinch.update(right_metric)

        # A middle-finger pinch tends to close the index gate too on most
        # hands, so give the right click priority and suppress the left.
        if right_pinched:
            left_pinched = False
            self._left_pinch.state = False
            if self._right_edge.update(True) and self._right_cooldown.try_fire():
                sample.right_fire = True
        else:
            self._right_edge.update(False)

        now = time.perf_counter()
        if left_pinched:
            if self._pinch_started is None:
                self._pinch_started = now
            if (now - self._pinch_started) * 1000.0 >= self.cfg.drag_hold_ms:
                self._dragging = True
            sample.left_down = True
        else:
            self._pinch_started = None
            self._dragging = False

        # Pinching curls the fingers, which nudges even the palm centre a
        # little. Freeze during the transition, but never during a long drag,
        # because you have to be able to move while dragging.
        sample.click_disturbance = right_pinched or (left_pinched and not self._dragging)

        # Report the right-click too. Without it a middle-finger pinch shows
        # as plain "move", which gives no feedback that the click registered
        # and leaves the trainer card unable to highlight the gesture.
        if right_pinched:
            gesture = "RIGHT"
        elif self._dragging:
            gesture = "DRAG"
        elif left_pinched:
            gesture = "CLICK"
        else:
            gesture = "move"

        sample.debug = {
            "gesture": gesture,
            "fingers": _finger_text(extended),
            "pinch L": f"{left_metric:.2f} (on<{self.cfg.pinch_on})",
            "pinch R": f"{right_metric:.2f} (on<{self.cfg.pinch_on})",
        }
        return sample

    def _release_everything(self, sample: Sample) -> None:
        self._pinch_started = None
        self._dragging = False
        self._left_pinch.state = False
        self._right_pinch.state = False
        sample.left_down = False

    def _lost(self) -> Sample:
        # Tracking dropped out. Clear gesture state so the engine releases any
        # held button rather than leaving the desktop with a stuck mouse-down.
        self._pinch_started = None
        self._dragging = False
        self._last_scroll_y = None
        self._left_pinch.state = False
        self._right_pinch.state = False
        return Sample(ok=False, parked=True, debug={"gesture": "no hand"})

    def reset(self) -> None:
        self._lost()

    def close(self) -> None:
        self._landmarker.close()
