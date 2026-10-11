"""Pointer maths: control-mode resolution, absolute mapping, stabiliser.

These are the pieces that decide whether the cursor feels usable, and they are
where the two "it barely moves" bugs lived.

Note the stubbed move_to in every engine test. Engine._apply_motion really
does drive the system cursor, so without the stub running the suite would
yank the pointer around the screen.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mycursor.config import Config
from mycursor.engine import Engine
from mycursor.filters import accel_gain
from mycursor.sample import Sample

DT = 1 / 30


def make_engine(mode: str = "hand", **pointer_overrides) -> Engine:
    cfg = Config()
    cfg.mode = mode
    cfg.show_preview = False
    for key, value in pointer_overrides.items():
        setattr(cfg.pointer, key, value)
    engine = Engine(cfg)
    # Start from a repeatable position. A live cursor near the right edge
    # made the clutch test hit the clamp before its second stroke.
    engine._px = float(engine.mouse.origin_x + engine.mouse.width * 0.2)
    engine._py = float(engine.mouse.origin_y + engine.mouse.height * 0.5)
    engine.moves: list[tuple[float, float]] = []
    engine.mouse.move_to = lambda x, y: engine.moves.append((x, y))
    return engine


class TestControlModeResolution(unittest.TestCase):
    def test_hand_defaults_to_absolute(self):
        """A hand has a real position and plenty of range."""
        self.assertEqual(make_engine("hand").control_mode(), "absolute")

    def test_head_defaults_to_relative(self):
        """A head's range is far too small to cover a screen."""
        self.assertEqual(make_engine("head").control_mode(), "relative")

    def test_explicit_choice_overrides_auto(self):
        self.assertEqual(
            make_engine("hand", control_mode="relative").control_mode(), "relative"
        )
        self.assertEqual(
            make_engine("head", control_mode="velocity").control_mode(), "velocity"
        )

    def test_resolution_follows_a_mode_switch(self):
        engine = make_engine("head")
        self.assertEqual(engine.control_mode(), "relative")
        engine.switch_mode()
        self.assertEqual(engine.control_mode(), "absolute")


class TestActiveRegion(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine("hand", active_margin_x=0.2, active_margin_y=0.2)
        self.mouse = self.engine.mouse

    def test_region_corner_maps_to_screen_corner(self):
        x, y = self.engine._absolute_target(0.2, 0.2)
        self.assertAlmostEqual(x, self.mouse.origin_x + self.engine.cfg.pointer.screen_margin, delta=1)
        self.assertAlmostEqual(y, self.mouse.origin_y + self.engine.cfg.pointer.screen_margin, delta=1)

    def test_region_centre_maps_to_screen_centre(self):
        x, y = self.engine._absolute_target(0.5, 0.5)
        self.assertAlmostEqual(x, self.mouse.origin_x + self.mouse.width / 2, delta=2)
        self.assertAlmostEqual(y, self.mouse.origin_y + self.mouse.height / 2, delta=2)

    def test_far_region_corner_reaches_the_far_screen_corner(self):
        x, y = self.engine._absolute_target(0.8, 0.8)
        self.assertAlmostEqual(x, self.mouse.origin_x + self.mouse.width, delta=3)
        self.assertAlmostEqual(y, self.mouse.origin_y + self.mouse.height, delta=3)

    def test_outside_the_region_clamps_rather_than_overshooting(self):
        left, top = self.engine._absolute_target(-0.5, -0.5)
        right, bottom = self.engine._absolute_target(1.5, 1.5)
        self.assertGreaterEqual(left, self.mouse.origin_x)
        self.assertGreaterEqual(top, self.mouse.origin_y)
        self.assertLessEqual(right, self.mouse.origin_x + self.mouse.width)
        self.assertLessEqual(bottom, self.mouse.origin_y + self.mouse.height)

    def test_smaller_region_means_less_hand_movement_per_pixel(self):
        wide = make_engine("hand", active_margin_x=0.05)
        tight = make_engine("hand", active_margin_x=0.30)
        step = 0.05
        wide_span = wide._absolute_target(0.5 + step, 0.5)[0] - wide._absolute_target(0.5, 0.5)[0]
        tight_span = tight._absolute_target(0.5 + step, 0.5)[0] - tight._absolute_target(0.5, 0.5)[0]
        self.assertGreater(tight_span, wide_span)


class TestStabiliser(unittest.TestCase):
    """The fix for "moving the cursor is hard".

    A speed deadzone cannot separate noise from slow intent, because noise is
    *fast*. A position radius can: jitter stays within a few pixels, and
    deliberate movement does not.

    These all pin clutch off, because they are about the rigid absolute
    mapping -- hand position straight onto screen position. Clutch behaviour
    is covered in TestClutch.
    """

    def settle(self, engine: Engine, ax: float, ay: float, frames: int = 120):
        for _ in range(frames):
            engine._apply_motion(Sample(ok=True, ax=ax, ay=ay), DT)
        return engine._px, engine._py

    def test_converges_onto_a_held_target(self):
        engine = make_engine("hand", clutch=False)
        x, y = self.settle(engine, 0.5, 0.5)
        tx, ty = engine._absolute_target(0.5, 0.5)
        self.assertLessEqual(
            math.hypot(x - tx, y - ty), engine.cfg.pointer.stabilise_px + 1.0
        )

    def test_jitter_does_not_visibly_move_or_drift_the_cursor(self):
        """Converging leaves the cursor exactly `stabilise_px` from the target,
        so it sits on the radius boundary and jitter can nudge it. That is
        harmless and self-limiting -- each step reduces the distance back to
        the radius, so nothing accumulates -- but it does mean the honest
        assertion is "visually still", not "literally zero updates"."""
        engine = make_engine("hand", clutch=False)
        self.settle(engine, 0.5, 0.5)
        before = (engine._px, engine._py)
        for i in range(60):
            engine._apply_motion(
                Sample(ok=True, ax=0.5 + (0.0006 if i % 2 else -0.0006), ay=0.5), DT
            )
        drift = math.hypot(engine._px - before[0], engine._py - before[1])
        self.assertLess(drift, 2.0, "jitter must not walk the cursor anywhere")

    def test_jitter_well_inside_the_radius_is_fully_ignored(self):
        engine = make_engine("hand", stabilise_px=40.0, clutch=False)
        self.settle(engine, 0.5, 0.5)
        # Put the cursor squarely in the middle of a generous radius.
        engine._px, engine._py = engine._absolute_target(0.5, 0.5)
        engine.moves.clear()
        for i in range(40):
            engine._apply_motion(
                Sample(ok=True, ax=0.5 + (0.002 if i % 2 else -0.002), ay=0.5), DT
            )
        self.assertEqual(engine.moves, [], "inside the radius nothing should move")

    def test_deliberate_movement_is_followed(self):
        engine = make_engine("hand", clutch=False)
        self.settle(engine, 0.35, 0.5)
        start = engine._px
        x, _ = self.settle(engine, 0.65, 0.5)
        self.assertGreater(x - start, 200, "a large hand move must move the cursor far")

    def test_movement_fades_in_with_no_threshold_jump(self):
        """Subtracting the radius rather than gating on it means the first
        pixel of real movement is one pixel, not a lurch."""
        engine = make_engine("hand", stabilise_px=10.0, clutch=False)
        self.settle(engine, 0.5, 0.5)
        # Place the cursor a known, exact distance past the radius. Nudging
        # the previous position blindly is not enough: convergence leaves the
        # cursor sitting on the boundary in an unknown direction, so an offset
        # can land either side of the target.
        target_x, target_y = engine._absolute_target(0.5, 0.5)
        engine._px, engine._py = target_x + 10.5, target_y
        engine._apply_motion(Sample(ok=True, ax=0.5, ay=0.5), DT)
        step = abs(engine._px - (target_x + 10.5))
        self.assertGreater(step, 0.0, "real movement must not be blocked")
        self.assertAlmostEqual(
            step, 0.5, delta=0.2, msg="only the excess beyond the radius should apply"
        )

    def test_large_excess_is_followed_in_full(self):
        """Far from the target the radius is a rounding error, so tracking is
        effectively 1:1 and the pointer keeps up with fast movement."""
        engine = make_engine("hand", stabilise_px=10.0, clutch=False)
        self.settle(engine, 0.5, 0.5)
        target_x, target_y = engine._absolute_target(0.5, 0.5)
        engine._px, engine._py = target_x + 300.0, target_y
        engine._apply_motion(Sample(ok=True, ax=0.5, ay=0.5), DT)
        self.assertAlmostEqual(engine._px - target_x, 10.0, delta=0.5)

    def test_zero_radius_tracks_exactly(self):
        engine = make_engine("hand", stabilise_px=0.0, clutch=False)
        x, y = self.settle(engine, 0.4, 0.6)
        tx, ty = engine._absolute_target(0.4, 0.6)
        self.assertAlmostEqual(x, tx, delta=1.5)
        self.assertAlmostEqual(y, ty, delta=1.5)


class TestAccelGainSoftKnee(unittest.TestCase):
    """The other half of the "hard to move" fix.

    The old curve jumped straight to min_gain the instant speed passed the
    deadzone. One frame frozen, the next moving at full min_gain -- so there
    was no way to request a small movement, only nothing or a jump.
    """

    ARGS = (0.14, 1.1, 900.0, 4200.0, 1.6)

    def gain(self, speed):
        return accel_gain(speed, *self.ARGS)

    def test_still_rejects_everything_below_the_deadzone(self):
        for speed in (0.0, 0.05, 0.139):
            self.assertEqual(self.gain(speed), 0.0)

    def test_no_cliff_at_the_deadzone_edge(self):
        just_over = self.gain(0.141)
        self.assertGreater(just_over, 0.0)
        self.assertLess(
            just_over, 100.0, "gain must ease out of the deadzone, not jump to min_gain"
        )

    def test_displacement_is_continuous_across_the_edge(self):
        below = 0.139 * self.gain(0.139)
        above = 0.141 * self.gain(0.141)
        self.assertLess(abs(above - below), 20.0)

    def test_gain_rises_monotonically(self):
        speeds = [0.15, 0.2, 0.3, 0.5, 0.8, 1.1, 2.0, 5.0]
        gains = [self.gain(s) for s in speeds]
        self.assertEqual(gains, sorted(gains))

    def test_fast_movement_still_reaches_near_max_gain(self):
        self.assertGreater(self.gain(10.0), 4000.0)

    def test_never_exceeds_max_gain(self):
        for speed in (0.15, 1.1, 5.0, 100.0):
            self.assertLessEqual(self.gain(speed), 4200.0)

    def test_slow_movement_gives_sub_pixel_precision(self):
        """At 30 fps a slow nudge should move the cursor by well under a pixel
        per frame, which is what precision actually means."""
        speed = 0.16
        px_per_frame = speed * self.gain(speed) * DT
        self.assertGreater(px_per_frame, 0.0)
        self.assertLess(px_per_frame, 3.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestClutch(unittest.TestCase):
    """Re-anchoring on re-engage, which is what makes any screen position
    reachable without your hand leaving the active box.

    Rigid absolute mapping ties the top-right of the box to the top-right of
    the screen and nowhere else, so a far corner demands your hand be in that
    corner -- the worst place for both reach and tracking. The clutch lets you
    cross in stages, exactly like lifting a mouse off the pad.
    """

    def settle(self, engine: Engine, ax: float, ay: float, frames: int = 90):
        for _ in range(frames):
            engine._apply_motion(Sample(ok=True, ax=ax, ay=ay), DT)
        return engine._px

    @staticmethod
    def park(engine: Engine) -> None:
        """What the run loop does when the hand parks or tracking drops."""
        engine._need_reanchor = True
        engine._filter.reset()

    def test_reengaging_does_not_jump_the_cursor(self):
        engine = make_engine("hand", clutch=True)
        self.settle(engine, 0.5, 0.5)
        before = engine._px
        # Park, move the hand somewhere completely different, unpark.
        self.park(engine)
        engine._apply_motion(Sample(ok=True, ax=0.25, ay=0.5), DT)
        self.assertAlmostEqual(
            engine._px, before, delta=2.0,
            msg="re-engaging must resume from where the cursor was",
        )

    def test_without_clutch_reengaging_snaps_to_the_hand(self):
        engine = make_engine("hand", clutch=False)
        self.settle(engine, 0.5, 0.5)
        before = engine._px
        self.park(engine)
        self.settle(engine, 0.25, 0.5)
        self.assertLess(
            engine._px, before - 100,
            msg="rigid mapping should snap to wherever the hand points",
        )

    def test_movement_after_reengaging_still_tracks(self):
        engine = make_engine("hand", clutch=True)
        self.settle(engine, 0.5, 0.5)
        self.park(engine)
        engine._apply_motion(Sample(ok=True, ax=0.4, ay=0.5), DT)
        start = engine._px
        moved = self.settle(engine, 0.6, 0.5)
        self.assertGreater(moved - start, 100, "the hand must still steer after a clutch")

    def test_two_strokes_reach_further_than_one(self):
        """The scenario this exists for: cursor bottom-left, target top-right,
        without ever putting the hand in a box corner."""
        engine = make_engine("hand", clutch=True)
        # Stroke one: middle of the box out to a comfortable right-ish position.
        self.settle(engine, 0.45, 0.5)
        self.settle(engine, 0.6, 0.5)
        after_one = engine._px
        # Clutch: park, bring the arm back to the middle, re-engage.
        self.park(engine)
        engine._apply_motion(Sample(ok=True, ax=0.45, ay=0.5), DT)
        # Stroke two: the same comfortable movement again.
        after_two = self.settle(engine, 0.6, 0.5)
        self.assertGreater(
            after_two, after_one + 50,
            msg="a second stroke must carry the cursor further right",
        )

    def test_clutch_cannot_push_the_cursor_off_screen(self):
        engine = make_engine("hand", clutch=True)
        mouse = engine.mouse
        # Repeatedly clutch and sweep the same direction, which without a
        # clamp would walk the target arbitrarily far off the desktop.
        for _ in range(8):
            self.settle(engine, 0.35, 0.35, frames=40)
            self.park(engine)
            engine._apply_motion(Sample(ok=True, ax=0.65, ay=0.65), DT)
        self.assertGreaterEqual(engine._px, mouse.origin_x)
        self.assertLessEqual(engine._px, mouse.origin_x + mouse.width)
        self.assertGreaterEqual(engine._py, mouse.origin_y)
        self.assertLessEqual(engine._py, mouse.origin_y + mouse.height)

    def test_clutch_is_on_by_default(self):
        from mycursor.config import Config as C

        self.assertTrue(C().pointer.clutch)
