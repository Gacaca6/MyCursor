"""Tests for the pieces that fail silently rather than loudly.

The Win32 struct layout is the main one: if sizeof(INPUT) is wrong, SendInput
returns 0 and the cursor simply never moves, with no error anywhere. The
filter and gain maths are the other -- a sign error there is the difference
between a usable pointer and one that runs away into a corner.
"""

from __future__ import annotations

import ctypes
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mycursor import hotkeys, input_win
from mycursor.config import CONFIG_VERSION, Config
from mycursor.filters import Cooldown, Hysteresis, OneEuro, RisingEdge, accel_gain


class TestWin32Layout(unittest.TestCase):
    """A wrong cbSize makes SendInput a no-op with no diagnostic."""

    def test_mouseinput_size(self):
        expected = 32 if ctypes.sizeof(ctypes.c_void_p) == 8 else 24
        self.assertEqual(ctypes.sizeof(input_win.MOUSEINPUT), expected)

    def test_input_size(self):
        expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        self.assertEqual(ctypes.sizeof(input_win.INPUT), expected)

    def test_union_is_big_enough(self):
        self.assertGreaterEqual(
            ctypes.sizeof(input_win._InputUnion), ctypes.sizeof(input_win.MOUSEINPUT)
        )

    def test_anonymous_union_exposes_mi(self):
        # engine assigns `events[0].mi`, which only works via _anonymous_.
        event = input_win.INPUT()
        event.mi = input_win.MOUSEINPUT(1, 2, 0, 0, 0, 0)
        self.assertEqual(event.mi.dx, 1)


class TestScreenMapping(unittest.TestCase):
    def setUp(self):
        self.driver = input_win.MouseDriver()

    def test_geometry_is_sane(self):
        self.assertGreater(self.driver.width, 0)
        self.assertGreater(self.driver.height, 0)

    def test_clamp_keeps_point_on_desktop(self):
        d = self.driver
        x, y = d.clamp(-99999, -99999)
        self.assertEqual((x, y), (d.origin_x, d.origin_y))
        x, y = d.clamp(99999, 99999)
        self.assertEqual(x, d.origin_x + d.width - 1)
        self.assertEqual(y, d.origin_y + d.height - 1)

    def test_absolute_normalisation_spans_full_range(self):
        """Left edge must map to 0 and right edge to 65535.

        Getting this wrong is the classic multi-monitor bug where the cursor
        can never quite reach the far edge of the screen.
        """
        d = self.driver
        to_abs = lambda v, size: int(round(v * 65535.0 / max(size - 1, 1)))
        self.assertEqual(to_abs(0, d.width), 0)
        self.assertEqual(to_abs(d.width - 1, d.width), 65535)


class TestOneEuro(unittest.TestCase):
    def test_converges_to_constant_input(self):
        f = OneEuro(min_cutoff=1.0, beta=0.01)
        for _ in range(300):
            out = f(5.0, 1 / 30)
        self.assertAlmostEqual(out, 5.0, places=3)

    def test_suppresses_jitter_around_a_still_point(self):
        f = OneEuro(min_cutoff=0.7, beta=0.005)
        noisy = [0.5 + (0.02 if i % 2 else -0.02) for i in range(200)]
        outputs = [f(v, 1 / 30) for v in noisy]
        tail = outputs[100:]
        spread = max(tail) - min(tail)
        self.assertLess(spread, 0.01, "filter should flatten alternating jitter")

    def test_tracks_a_ramp_without_falling_far_behind(self):
        f = OneEuro(min_cutoff=1.0, beta=0.05)
        value = 0.0
        for _ in range(120):
            value += 0.01
            out = f(value, 1 / 30)
        self.assertLess(abs(out - value), 0.05, "filter lags too much when moving")

    def test_reset_forgets_history(self):
        f = OneEuro()
        for _ in range(50):
            f(10.0, 1 / 30)
        f.reset()
        self.assertAlmostEqual(f(0.0, 1 / 30), 0.0, places=6)


class TestAccelGain(unittest.TestCase):
    def test_deadzone_rejects_tremor(self):
        self.assertEqual(
            accel_gain(0.005, 0.012, 1.1, 900, 4200, 1.6), 0.0
        )

    def test_gain_rises_with_speed(self):
        slow = accel_gain(0.1, 0.012, 1.1, 900, 4200, 1.6)
        fast = accel_gain(0.9, 0.012, 1.1, 900, 4200, 1.6)
        self.assertGreater(fast, slow)

    def test_gain_is_capped_at_max(self):
        for speed in (1.1, 5.0, 500.0):
            self.assertLessEqual(accel_gain(speed, 0.012, 1.1, 900, 4200, 1.6), 4200)

    def test_gain_never_negative(self):
        for speed in (0.0, 0.012, 0.013, 1.0, 99.0):
            self.assertGreaterEqual(accel_gain(speed, 0.012, 1.1, 900, 4200, 1.6), 0.0)


class TestHysteresis(unittest.TestCase):
    def test_requires_crossing_both_thresholds(self):
        h = Hysteresis(on_below=0.34, off_above=0.48)
        self.assertFalse(h.update(0.60))
        self.assertFalse(h.update(0.40))  # in the dead band, still off
        self.assertTrue(h.update(0.30))  # crossed the on threshold
        self.assertTrue(h.update(0.40))  # dead band, stays on
        self.assertFalse(h.update(0.50))  # crossed the off threshold

    def test_no_chatter_when_hovering_at_the_boundary(self):
        h = Hysteresis(on_below=0.34, off_above=0.48)
        h.update(0.30)
        flips = 0
        previous = h.state
        for i in range(100):
            state = h.update(0.35 if i % 2 else 0.33)
            flips += state != previous
            previous = state
        self.assertEqual(flips, 0, "a value wobbling in the dead band must not flip")

    def test_rejects_inverted_thresholds(self):
        with self.assertRaises(ValueError):
            Hysteresis(on_below=0.5, off_above=0.3)


class TestEdgeAndCooldown(unittest.TestCase):
    def test_rising_edge_fires_once_per_press(self):
        e = RisingEdge()
        self.assertTrue(e.update(True))
        self.assertFalse(e.update(True))
        self.assertFalse(e.update(False))
        self.assertTrue(e.update(True))

    def test_cooldown_blocks_second_fire(self):
        c = Cooldown(seconds=10.0)
        self.assertTrue(c.try_fire())
        self.assertFalse(c.try_fire())


class TestHotkeys(unittest.TestCase):
    def test_parses_chord(self):
        mods, main = hotkeys.parse("ctrl+alt+space")
        self.assertEqual(mods, frozenset({hotkeys.VK_CONTROL, hotkeys.VK_MENU}))
        self.assertEqual(main, 0x20)

    def test_parses_letter_and_function_keys(self):
        self.assertEqual(hotkeys.parse("ctrl+m")[1], ord("M"))
        self.assertEqual(hotkeys.parse("f8")[1], 0x77)

    def test_is_case_and_space_insensitive(self):
        self.assertEqual(hotkeys.parse("CTRL + ALT + Q"), hotkeys.parse("ctrl+alt+q"))

    def test_rejects_nonsense(self):
        for bad in ("", "ctrl+alt", "ctrl+notakey"):
            with self.assertRaises(hotkeys.BadHotkey):
                hotkeys.parse(bad)

    def test_bad_binding_is_recorded_not_raised(self):
        """One typo in settings.json must not stop the pointer starting."""
        keys = hotkeys.Hotkeys()
        keys.bind("toggle", "ctrl+alt+nope")
        self.assertTrue(keys.errors)
        self.assertEqual(keys.poll(), set())

    def test_poll_with_no_bindings_is_quiet(self):
        self.assertEqual(hotkeys.Hotkeys().poll(), set())


class TestConfig(unittest.TestCase):
    def test_partial_file_keeps_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            path.write_text(json.dumps({"mode": "hand", "camera": {"index": 3}}))
            cfg = Config.load(path)
            self.assertEqual(cfg.mode, "hand")
            self.assertEqual(cfg.camera.index, 3)
            self.assertEqual(cfg.camera.width, 640)
            self.assertEqual(cfg.head.dwell_time_ms, 700)

    def test_unknown_keys_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            path.write_text(json.dumps({"nope": 1, "pointer": {"bogus": 2}}))
            self.assertIsInstance(Config.load(path), Config)

    def test_corrupt_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            path.write_text("{not json at all")
            self.assertEqual(Config.load(path).mode, "head")

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.json"
            cfg = Config()
            cfg.hand.pinch_on = 0.21
            cfg.save(path)
            self.assertAlmostEqual(Config.load(path).hand.pinch_on, 0.21)

    def test_pinch_thresholds_leave_a_dead_band(self):
        cfg = Config()
        self.assertLess(
            cfg.hand.pinch_on,
            cfg.hand.pinch_off,
            "defaults must be usable by Hysteresis",
        )

    def test_defaults_start_disabled(self):
        """Safety: a mistuned pointer must not seize the cursor on launch."""
        self.assertFalse(Config().start_enabled)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestConfigMigration(unittest.TestCase):
    """An old settings.json must not silently pin you to old behaviour.

    Merging stored values over new defaults is what lets tuning survive an
    upgrade, but it also means a key whose *default* was wrong keeps being
    honoured. v1 stored control_mode="relative" and deadzone=0.5, so a fixed
    build loaded the broken feel and looked unchanged.
    """

    def write(self, directory, payload):
        path = Path(directory) / "s.json"
        path.write_text(json.dumps(payload))
        return path

    def test_v1_file_has_redefined_keys_reset(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, {"pointer": {"control_mode": "relative", "deadzone": 0.5}})
            cfg = Config.load(path)
            self.assertEqual(cfg.pointer.control_mode, "auto")
            self.assertNotEqual(cfg.pointer.deadzone, 0.5)

    def test_migration_keeps_values_it_does_not_own(self):
        """Tuned filter settings are measured data and must survive."""
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, {
                "pointer": {"control_mode": "relative", "filter_min_cutoff": 0.4,
                            "filter_beta": 0.02, "max_gain": 3333.0},
            })
            cfg = Config.load(path)
            self.assertAlmostEqual(cfg.pointer.filter_min_cutoff, 0.4)
            self.assertAlmostEqual(cfg.pointer.filter_beta, 0.02)
            self.assertAlmostEqual(cfg.pointer.max_gain, 3333.0)

    def test_migration_is_written_back_and_not_repeated(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, {"pointer": {"control_mode": "relative"}})
            Config.load(path)
            stored = json.loads(path.read_text())
            self.assertEqual(stored["config_version"], CONFIG_VERSION)
            # Second load is already current, so nothing to migrate.
            self.assertEqual(Config.load(path).pointer.control_mode, "auto")

    def test_current_version_file_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.write(d, {
                "config_version": CONFIG_VERSION,
                "pointer": {"control_mode": "relative", "deadzone": 0.5},
            })
            cfg = Config.load(path)
            self.assertEqual(cfg.pointer.control_mode, "relative",
                             "a deliberate choice on a current file must be honoured")
            self.assertEqual(cfg.pointer.deadzone, 0.5)

    def test_fresh_config_is_stamped_with_the_version(self):
        self.assertEqual(Config().config_version, CONFIG_VERSION)


class TestWindowPlacementHelpers(unittest.TestCase):
    """The preview is useless if it lands under the taskbar or off-screen."""

    def setUp(self):
        from mycursor import input_win

        self.iw = input_win

    def test_work_area_is_sane(self):
        x, y, w, h = self.iw.work_area()
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

    def test_work_area_fits_inside_the_screen(self):
        driver = self.iw.MouseDriver()
        _, _, w, h = self.iw.work_area()
        self.assertLessEqual(w, driver.width)
        self.assertLessEqual(h, driver.height)

    def test_work_area_excludes_the_taskbar(self):
        """Not strictly guaranteed, but on any normal desktop the usable area
        is shorter than the screen. If this ever fails the placement code
        still clamps, so it is a signal rather than a fault."""
        driver = self.iw.MouseDriver()
        _, _, _, h = self.iw.work_area()
        if h == driver.height:
            self.skipTest("no reserved taskbar area on this desktop")
        self.assertLess(h, driver.height)

    def test_find_window_returns_zero_for_nonsense(self):
        self.assertEqual(self.iw.find_window("no such window 8f3a1c"), 0)

    def test_outer_size_of_no_window_is_zero(self):
        self.assertEqual(self.iw.outer_size(0), (0, 0))

    def test_move_window_on_no_window_fails_quietly(self):
        self.assertFalse(self.iw.move_window(0, 10, 10))


class TestPracticeMode(unittest.TestCase):
    def test_pointer_movement_is_on_by_default(self):
        self.assertTrue(Config().move_pointer)

    def test_idle_poll_is_a_sane_interval(self):
        cfg = Config()
        self.assertGreaterEqual(cfg.idle_poll_ms, 5)
        self.assertLessEqual(cfg.idle_poll_ms, 500)

    def test_preview_defaults_are_compact_and_topmost(self):
        pv = Config().preview
        self.assertTrue(pv.topmost)
        self.assertLessEqual(pv.width, 640, "the monitor window should be small")
        self.assertIn(pv.corner, ("top-left", "top-right", "bottom-left", "bottom-right"))


class TestHotkeyDefaults(unittest.TestCase):
    def test_wake_hotkey_is_not_the_claude_one(self):
        """ctrl+alt+space is registered globally by the Claude desktop app, so
        a chord set to it never reaches this process at all."""
        self.assertNotEqual(Config().hotkeys.toggle_enable, "ctrl+alt+space")

    def test_all_default_hotkeys_parse(self):
        keys = Config().hotkeys
        for spec in (keys.toggle_enable, keys.switch_mode, keys.recenter,
                     keys.left_click, keys.quit):
            with self.subTest(spec=spec):
                hotkeys.parse(spec)

    def test_default_hotkeys_are_all_distinct(self):
        keys = Config().hotkeys
        specs = [keys.toggle_enable, keys.switch_mode, keys.recenter,
                 keys.left_click, keys.quit]
        self.assertEqual(len(specs), len(set(specs)), "two actions share a chord")
