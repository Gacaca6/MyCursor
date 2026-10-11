"""Hand gesture logic, tested with synthetic landmarks.

The smoke test can only confirm the hand pipeline runs; it cannot confirm that
a pinch is read as a click, because that needs a hand in front of the camera at
a known pose. Here we feed the tracker hand-built landmark sets instead, which
pins down the gesture decisions exactly and needs no camera and no model.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mycursor.config import HandConfig
from mycursor.tracker_hand import (
    INDEX_PIP,
    INDEX_TIP,
    MIDDLE_MCP,
    MIDDLE_PIP,
    MIDDLE_TIP,
    PINKY_PIP,
    PINKY_TIP,
    RING_PIP,
    RING_TIP,
    THUMB_TIP,
    WRIST,
    HandTracker,
)


class FakeLandmark:
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float, y: float, z: float = 0.0):
        self.x, self.y, self.z = x, y, z


class FakeResult:
    def __init__(self, landmarks):
        self.hand_landmarks = [landmarks] if landmarks else []
        self.handedness = [[]] if landmarks else []


WRIST_Y = 0.80
PIP_Y = 0.50  # 0.30 from the wrist
TIP_EXTENDED_Y = 0.35  # 0.45 from the wrist -> extended
TIP_CURLED_Y = 0.62  # 0.18 from the wrist -> curled
SCALE = 0.20  # wrist to middle knuckle


def make_hand(
    index_up: bool = True,
    middle_up: bool = True,
    ring_up: bool = True,
    pinky_up: bool = True,
    thumb_index_gap: float = 0.14,
    thumb_middle_gap: float = 0.14,
) -> list[FakeLandmark]:
    """Build a 21-point hand.

    Gaps are in normalised frame units; the tracker divides them by the hand
    scale (0.20 here), so a gap of 0.05 becomes a pinch metric of 0.25.
    """
    points = [FakeLandmark(0.5, 0.5) for _ in range(21)]
    points[WRIST] = FakeLandmark(0.50, WRIST_Y)
    points[MIDDLE_MCP] = FakeLandmark(0.50, WRIST_Y - SCALE)

    layout = (
        (INDEX_TIP, INDEX_PIP, index_up, 0.46),
        (MIDDLE_TIP, MIDDLE_PIP, middle_up, 0.50),
        (RING_TIP, RING_PIP, ring_up, 0.54),
        (PINKY_TIP, PINKY_PIP, pinky_up, 0.58),
    )
    for tip, pip, is_up, x in layout:
        points[pip] = FakeLandmark(x, PIP_Y)
        points[tip] = FakeLandmark(x, TIP_EXTENDED_Y if is_up else TIP_CURLED_Y)

    # Place the thumb so both pinch distances come out as requested. The
    # index gap is the one that decides a left click, so honour it exactly and
    # position along x from the index tip.
    index_tip = points[INDEX_TIP]
    points[THUMB_TIP] = FakeLandmark(index_tip.x - thumb_index_gap, index_tip.y)
    if thumb_middle_gap < thumb_index_gap:
        middle_tip = points[MIDDLE_TIP]
        points[THUMB_TIP] = FakeLandmark(
            middle_tip.x - thumb_middle_gap, middle_tip.y
        )
    return points


def make_tracker(cfg: HandConfig | None = None, mirror: bool = False) -> HandTracker:
    """A HandTracker with the model replaced by a stub.

    __init__ is bypassed so no model file is loaded and no camera is needed.
    """
    from mycursor.filters import Cooldown, Hysteresis, RisingEdge

    cfg = cfg or HandConfig()
    tracker = object.__new__(HandTracker)
    tracker.cfg = cfg
    tracker.mirror = mirror
    tracker._left_pinch = Hysteresis(cfg.pinch_on, cfg.pinch_off)
    tracker._right_pinch = Hysteresis(cfg.pinch_on, cfg.pinch_off)
    tracker._right_edge = RisingEdge()
    tracker._right_cooldown = Cooldown(0.35)
    tracker._pinch_started = None
    tracker._dragging = False
    tracker._last_scroll_y = None
    tracker._last_ts = 0

    class StubMp:
        ImageFormat = type("F", (), {"SRGB": 0})

        @staticmethod
        def Image(image_format=None, data=None):
            return None

    tracker._mp = StubMp
    tracker._pending = None

    class StubLandmarker:
        def detect_for_video(self, image, ts):
            return FakeResult(tracker._pending)

        def close(self):
            pass

    tracker._landmarker = StubLandmarker()
    return tracker


def feed(tracker: HandTracker, landmarks, ts: int = 0):
    tracker._pending = landmarks
    return tracker.process(None, ts)


class TestGeometryHelpers(unittest.TestCase):
    def test_hand_scale_is_wrist_to_middle_knuckle(self):
        self.assertAlmostEqual(HandTracker._hand_scale(make_hand()), SCALE, places=6)

    def test_scale_ignores_finger_pose(self):
        """The scale reference must not change when fingers curl, or every
        gesture threshold would drift as you move your hand."""
        open_scale = HandTracker._hand_scale(make_hand())
        fist_scale = HandTracker._hand_scale(
            make_hand(index_up=False, middle_up=False, ring_up=False, pinky_up=False)
        )
        self.assertAlmostEqual(open_scale, fist_scale, places=6)

    def test_extension_detection(self):
        self.assertEqual(HandTracker._extended(make_hand()), (True, True, True, True))
        self.assertEqual(
            HandTracker._extended(
                make_hand(index_up=False, middle_up=False, ring_up=False, pinky_up=False)
            ),
            (False, False, False, False),
        )
        self.assertEqual(
            HandTracker._extended(make_hand(ring_up=False, pinky_up=False)),
            (True, True, False, False),
        )


class TestAnchor(unittest.TestCase):
    def test_palm_anchor_is_midpoint_of_wrist_and_knuckle(self):
        # A curled hand: an open palm would hit the park branch and
        # index+middle up would hit the scroll branch, neither of which
        # reports a usable anchor.
        sample = feed(
            make_tracker(),
            make_hand(index_up=False, middle_up=False, ring_up=False, pinky_up=False),
            1,
        )
        self.assertTrue(sample.ok)
        self.assertAlmostEqual(sample.ax, 0.50, places=6)
        self.assertAlmostEqual(sample.ay, WRIST_Y - SCALE / 2, places=6)

    def test_index_tip_anchor_when_configured(self):
        cfg = HandConfig()
        cfg.cursor_anchor = "index_tip"
        tracker = make_tracker(cfg)
        sample = feed(
            tracker,
            make_hand(index_up=False, middle_up=False, ring_up=False, pinky_up=False),
            1,
        )
        self.assertAlmostEqual(sample.ay, TIP_CURLED_Y, places=6)

    def test_mirror_flips_x_only(self):
        pose = make_hand(index_up=False, middle_up=False, ring_up=False, pinky_up=False)
        plain = feed(make_tracker(mirror=False), pose, 1)
        flipped = feed(make_tracker(mirror=True), pose, 1)
        self.assertAlmostEqual(flipped.ax, 1.0 - plain.ax, places=6)
        self.assertAlmostEqual(flipped.ay, plain.ay, places=6)

    def test_palm_anchor_is_stable_while_pinching(self):
        """The whole reason we anchor on the palm: a click must not move it."""
        tracker = make_tracker()
        open_pose = feed(
            tracker,
            make_hand(index_up=False, middle_up=False, ring_up=False, pinky_up=False,
                      thumb_index_gap=0.14),
            1,
        )
        pinched = feed(
            tracker,
            make_hand(index_up=False, middle_up=False, ring_up=False, pinky_up=False,
                      thumb_index_gap=0.04),
            2,
        )
        self.assertAlmostEqual(open_pose.ax, pinched.ax, places=6)
        self.assertAlmostEqual(open_pose.ay, pinched.ay, places=6)


class TestPark(unittest.TestCase):
    def test_open_palm_parks(self):
        sample = feed(make_tracker(), make_hand(), 1)
        self.assertTrue(sample.parked)
        self.assertFalse(sample.left_down)

    def test_park_can_be_disabled(self):
        cfg = HandConfig()
        cfg.park_on_open_palm = False
        sample = feed(make_tracker(cfg), make_hand(), 1)
        self.assertFalse(sample.parked)

    def test_no_hand_reports_not_ok(self):
        sample = feed(make_tracker(), None, 1)
        self.assertFalse(sample.ok)
        self.assertTrue(sample.parked)


class TestClicks(unittest.TestCase):
    @staticmethod
    def fist(**kwargs):
        base = dict(index_up=False, middle_up=False, ring_up=False, pinky_up=False)
        base.update(kwargs)
        return make_hand(**base)

    def test_pinch_presses_left(self):
        tracker = make_tracker()
        sample = feed(tracker, self.fist(thumb_index_gap=0.04), 1)
        self.assertTrue(sample.left_down)

    def test_open_fingers_do_not_click(self):
        tracker = make_tracker()
        sample = feed(tracker, self.fist(thumb_index_gap=0.14), 1)
        self.assertFalse(sample.left_down)

    def test_pinch_freezes_motion_but_a_drag_does_not(self):
        """You must be able to move while dragging, but not while clicking."""
        cfg = HandConfig()
        tracker = make_tracker(cfg)
        first = feed(tracker, self.fist(thumb_index_gap=0.04), 1)
        self.assertTrue(first.click_disturbance)

        # Backdate the pinch so it has been held past the drag threshold.
        tracker._pinch_started = time.perf_counter() - (cfg.drag_hold_ms / 1000.0) - 0.1
        later = feed(tracker, self.fist(thumb_index_gap=0.04), 2)
        self.assertTrue(later.left_down)
        self.assertFalse(later.click_disturbance, "a held drag must not freeze motion")
        self.assertEqual(later.debug["gesture"], "DRAG")

    def test_hysteresis_prevents_click_chatter(self):
        """A gap wobbling in the dead band must not produce a burst of clicks."""
        tracker = make_tracker()
        feed(tracker, self.fist(thumb_index_gap=0.04), 1)  # engage
        transitions = 0
        previous = True
        for i in range(2, 40):
            gap = 0.076 if i % 2 else 0.082  # metric 0.38 / 0.41, inside the band
            sample = feed(tracker, self.fist(thumb_index_gap=gap), i)
            transitions += sample.left_down != previous
            previous = sample.left_down
        self.assertEqual(transitions, 0)

    def test_releasing_clears_left(self):
        tracker = make_tracker()
        feed(tracker, self.fist(thumb_index_gap=0.04), 1)
        released = feed(tracker, self.fist(thumb_index_gap=0.14), 2)
        self.assertFalse(released.left_down)

    def test_middle_pinch_fires_right_click_once(self):
        tracker = make_tracker()
        first = feed(tracker, self.fist(thumb_index_gap=0.20, thumb_middle_gap=0.04), 1)
        self.assertTrue(first.right_fire)
        second = feed(tracker, self.fist(thumb_index_gap=0.20, thumb_middle_gap=0.04), 2)
        self.assertFalse(second.right_fire, "right click must be one-shot, not repeating")

    def test_right_click_suppresses_left(self):
        """A middle pinch closes the index gap too on most hands."""
        tracker = make_tracker()
        sample = feed(tracker, self.fist(thumb_index_gap=0.04, thumb_middle_gap=0.03), 1)
        self.assertTrue(sample.right_fire)
        self.assertFalse(sample.left_down)

    def test_losing_the_hand_clears_a_held_pinch(self):
        """Otherwise the desktop is left with a stuck mouse button."""
        tracker = make_tracker()
        feed(tracker, self.fist(thumb_index_gap=0.04), 1)
        lost = feed(tracker, None, 2)
        self.assertFalse(lost.left_down)
        recovered = feed(tracker, self.fist(thumb_index_gap=0.14), 3)
        self.assertFalse(recovered.left_down)


class TestScroll(unittest.TestCase):
    @staticmethod
    def two_fingers(**kwargs):
        base = dict(index_up=True, middle_up=True, ring_up=False, pinky_up=False)
        base.update(kwargs)
        return make_hand(**base)

    def test_two_finger_pose_enters_scroll_mode(self):
        sample = feed(make_tracker(), self.two_fingers(), 1)
        self.assertEqual(sample.debug["gesture"], "SCROLL")
        self.assertTrue(sample.parked, "must not also move the cursor while scrolling")

    def test_first_scroll_frame_emits_nothing(self):
        """There is no previous position to measure against yet."""
        sample = feed(make_tracker(), self.two_fingers(), 1)
        self.assertEqual(sample.scroll, 0.0)

    def test_moving_up_scrolls_up(self):
        tracker = make_tracker()
        feed(tracker, self.two_fingers(), 1)
        # Move the index tip up the frame (smaller y).
        pose = self.two_fingers()
        pose[INDEX_TIP] = FakeLandmark(pose[INDEX_TIP].x, pose[INDEX_TIP].y - 0.10)
        sample = feed(tracker, pose, 2)
        self.assertGreater(sample.scroll, 0.0)

    def test_moving_down_scrolls_down(self):
        tracker = make_tracker()
        feed(tracker, self.two_fingers(), 1)
        pose = self.two_fingers()
        pose[INDEX_TIP] = FakeLandmark(pose[INDEX_TIP].x, pose[INDEX_TIP].y + 0.10)
        sample = feed(tracker, pose, 2)
        self.assertLess(sample.scroll, 0.0)

    def test_tiny_movement_is_ignored(self):
        cfg = HandConfig()
        tracker = make_tracker(cfg)
        feed(tracker, self.two_fingers(), 1)
        pose = self.two_fingers()
        pose[INDEX_TIP] = FakeLandmark(
            pose[INDEX_TIP].x, pose[INDEX_TIP].y - cfg.scroll_deadzone / 2
        )
        self.assertEqual(feed(tracker, pose, 2).scroll, 0.0)


class TestTimestamps(unittest.TestCase):
    def test_repeated_timestamp_is_bumped(self):
        """MediaPipe rejects a non-increasing video timestamp, which happens
        whenever two frames land inside the same millisecond."""
        tracker = make_tracker()
        pose = make_hand(index_up=False, middle_up=False, ring_up=False, pinky_up=False)
        feed(tracker, pose, 100)
        feed(tracker, pose, 100)
        feed(tracker, pose, 100)
        self.assertGreater(tracker._last_ts, 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestExtensionMargin(unittest.TestCase):
    """The fix for scrolling never working.

    A bare tip-vs-joint comparison leaves a half-curled finger sitting on the
    boundary, flickering between states. Since the park gesture needs all four
    fingers extended, that flicker kept winning and the scroll pose never got
    a chance.
    """

    @staticmethod
    def half_curled():
        """A hand whose ring finger is only slightly past its joint."""
        pose = make_hand()
        # 0.315 from the wrist vs the joint's 0.30: past it, but only by 5%.
        pose[RING_TIP] = FakeLandmark(0.54, WRIST_Y - 0.315)
        return pose

    def test_bare_comparison_calls_it_extended(self):
        self.assertTrue(HandTracker._extended(self.half_curled(), margin=0.0)[2])

    def test_margin_calls_it_curled(self):
        self.assertFalse(HandTracker._extended(self.half_curled(), margin=0.12)[2])

    def test_clearly_extended_survives_the_margin(self):
        self.assertEqual(
            HandTracker._extended(make_hand(), margin=0.12), (True, True, True, True)
        )

    def test_half_curled_ring_now_reaches_scroll_instead_of_park(self):
        cfg = HandConfig()
        pose = self.half_curled()
        # With no margin the ring reads as up, so all four are up -> park.
        loose = make_tracker(HandConfig())
        loose.cfg.extend_margin = 0.0
        self.assertTrue(feed(loose, pose, 1).parked)
        # With the margin the ring reads as down -> the scroll pose matches.
        strict = make_tracker(cfg)
        self.assertEqual(feed(strict, pose, 1).debug["gesture"], "SCROLL")


class TestScrollRobustness(unittest.TestCase):
    def test_stray_pinky_does_not_block_scrolling(self):
        """The pinky is the least reliably tracked finger, so by default the
        scroll pose ignores it."""
        pose = make_hand(index_up=True, middle_up=True, ring_up=False, pinky_up=True)
        sample = feed(make_tracker(), pose, 1)
        self.assertEqual(sample.debug["gesture"], "SCROLL")

    def test_strict_mode_does_require_the_pinky_down(self):
        cfg = HandConfig()
        cfg.scroll_requires_pinky_down = True
        pose = make_hand(index_up=True, middle_up=True, ring_up=False, pinky_up=True)
        self.assertNotEqual(feed(make_tracker(cfg), pose, 1).debug["gesture"], "SCROLL")

    def test_scroll_is_preferred_over_park(self):
        """Scroll is the more specific pose, so it is tested first."""
        pose = make_hand(index_up=True, middle_up=True, ring_up=False, pinky_up=False)
        sample = feed(make_tracker(), pose, 1)
        self.assertEqual(sample.debug["gesture"], "SCROLL")
        self.assertNotIn("PARKED", sample.debug["gesture"])

    def test_open_palm_still_parks(self):
        self.assertIn("PARKED", feed(make_tracker(), make_hand(), 1).debug["gesture"])


class TestFingerReadout(unittest.TestCase):
    def test_renders_all_four_fingers(self):
        from mycursor.tracker_hand import _finger_text

        self.assertEqual(
            _finger_text((True, True, False, False)), "I:up M:up R:dn P:dn"
        )


class TestGestureLabels(unittest.TestCase):
    """The label is the only feedback the user gets, and the trainer card
    highlights rows by matching it, so every gesture must name itself."""

    @staticmethod
    def fist(**kwargs):
        base = dict(index_up=False, middle_up=False, ring_up=False, pinky_up=False)
        base.update(kwargs)
        return make_hand(**base)

    def test_right_click_names_itself(self):
        tracker = make_tracker()
        sample = feed(tracker, self.fist(thumb_index_gap=0.20, thumb_middle_gap=0.04), 1)
        self.assertTrue(sample.right_fire)
        self.assertEqual(sample.debug["gesture"], "RIGHT")

    def test_right_click_label_persists_while_held(self):
        """The one-shot click fires once, but the pose should keep reporting."""
        tracker = make_tracker()
        feed(tracker, self.fist(thumb_index_gap=0.20, thumb_middle_gap=0.04), 1)
        second = feed(tracker, self.fist(thumb_index_gap=0.20, thumb_middle_gap=0.04), 2)
        self.assertFalse(second.right_fire, "must not repeat the click")
        self.assertEqual(second.debug["gesture"], "RIGHT", "but should still report the pose")

    def test_every_row_of_the_trainer_can_light_up(self):
        """Each legend row must match a label the tracker actually emits."""
        from mycursor.engine import Engine

        emitted = set()
        tracker = make_tracker()
        emitted.add(feed(tracker, self.fist(thumb_index_gap=0.20), 1).debug["gesture"])
        emitted.add(feed(make_tracker(), self.fist(thumb_index_gap=0.04), 1).debug["gesture"])
        emitted.add(
            feed(make_tracker(), self.fist(thumb_index_gap=0.20, thumb_middle_gap=0.04), 1)
            .debug["gesture"]
        )
        emitted.add(
            feed(make_tracker(),
                 make_hand(index_up=True, middle_up=True, ring_up=False, pinky_up=False), 1)
            .debug["gesture"]
        )
        emitted.add(feed(make_tracker(), make_hand(), 1).debug["gesture"])

        # DRAG needs a held pinch, which the timing test covers separately.
        emitted.add("DRAG")

        for label, _hint, keys in Engine._GESTURE_ROWS:
            with self.subTest(row=label):
                self.assertTrue(
                    any(any(k.lower() in e.lower() for e in emitted) for k in keys),
                    f"no emitted gesture matches the {label!r} row: {sorted(emitted)}",
                )
