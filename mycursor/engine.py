"""The capture loop and all pointer arithmetic.

Both trackers report the same Sample, so everything that decides how the
cursor *feels* lives here exactly once: filtering, the acceleration curve,
click freezing, dwell, and the safety switch.
"""

from __future__ import annotations

import math
import time
from typing import Callable

import cv2
import numpy as np

from .config import Config
from .filters import OneEuro2D, accel_gain
from .hotkeys import Hotkeys
from .input_win import MouseDriver, find_window, move_window, outer_size, work_area
from .sample import Sample, Tracker

WINDOW = "MyCursor - preview"


class CameraError(RuntimeError):
    pass


def open_camera(index: int, width: int, height: int, fps: int):
    """Open a capture device, fastest working Windows backend first.

    Backend choice is not cosmetic here, it is the single biggest performance
    factor in the whole program. Measured on the integrated camera of a Lenovo
    V14 G3: Media Foundation returns a frame in ~4 ms, DirectShow takes ~97 ms
    and pins the whole pointer to 10 fps no matter what pixel format or
    resolution you ask it for. Inference only costs 25-32 ms, so with the wrong
    backend the camera, not the model, is what makes the cursor feel laggy.

    DirectShow stays as a fallback because it works on some devices that MSMF
    refuses to open at all.
    """
    attempts = [
        ("Media Foundation", cv2.CAP_MSMF),
        ("DirectShow", cv2.CAP_DSHOW),
        ("default", cv2.CAP_ANY),
    ]
    errors = []
    for label, backend in attempts:
        capture = cv2.VideoCapture(index, backend)
        if capture.isOpened():
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            capture.set(cv2.CAP_PROP_FPS, fps)
            # A deep driver buffer adds latency we would feel as pointer lag.
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, _ = capture.read()
            if ok:
                return capture, label
            capture.release()
            errors.append(f"{label}: opened but returned no frames")
        else:
            errors.append(f"{label}: could not open")
    raise CameraError(
        f"Could not start camera {index}.\n  "
        + "\n  ".join(errors)
        + "\n  Close anything else using the webcam (Teams, Zoom, Camera app),"
        "\n  and check Settings > Privacy & security > Camera."
    )


class Engine:
    def __init__(self, cfg: Config, on_state: Callable[[str], None] | None = None):
        self.cfg = cfg
        self.mouse = MouseDriver()
        self.on_state = on_state or (lambda _msg: None)

        self.mode = cfg.mode
        self.enabled = cfg.start_enabled
        self.running = True

        self._trackers: dict[str, Tracker] = {}
        self._filter = OneEuro2D(
            cfg.pointer.filter_min_cutoff,
            cfg.pointer.filter_beta,
            cfg.pointer.filter_d_cutoff,
        )

        # Cursor position is kept as floats so that sub-pixel movement
        # accumulates instead of being rounded away to nothing every frame.
        x, y = self.mouse.get_pos()
        self._px = float(x)
        self._py = float(y)

        self._prev_anchor: tuple[float, float] | None = None
        self._freeze_until = 0.0
        self._left_held = False

        # Dwell state (head mode).
        self._dwell_anchor: tuple[float, float] | None = None
        self._dwell_start = 0.0
        self._dwell_armed = True

        self._fps = 0.0
        self._preview_open = False
        self._show_legend = False
        # Offset between where the hand maps to and where the cursor actually
        # is. Zero means a rigid absolute mapping; the clutch sets it on every
        # re-engage so the cursor resumes from where it was left.
        self._anchor_offset = (0.0, 0.0)
        self._need_reanchor = True

        self.keys = Hotkeys()
        self.keys.bind("toggle", cfg.hotkeys.toggle_enable)
        self.keys.bind("mode", cfg.hotkeys.switch_mode)
        self.keys.bind("recenter", cfg.hotkeys.recenter)
        self.keys.bind("quit", cfg.hotkeys.quit)
        self.keys.bind("click", cfg.hotkeys.left_click)
        self.keys.bind("legend", cfg.hotkeys.legend)

    # --- tracker plumbing ----------------------------------------------
    def _tracker(self) -> Tracker:
        if self.mode not in self._trackers:
            if self.mode == "hand":
                from .tracker_hand import HandTracker

                self._trackers["hand"] = HandTracker(
                    self.cfg.hand, self.cfg.camera.mirror
                )
            else:
                from .tracker_head import HeadTracker

                self._trackers["head"] = HeadTracker(
                    self.cfg.head, self.cfg.camera.mirror
                )
        return self._trackers[self.mode]

    def set_enabled(self, value: bool) -> None:
        if value == self.enabled:
            return
        self.enabled = value
        if not value:
            # Never leave a button stuck down when the pointer is switched off.
            self.mouse.release_all()
            self._left_held = False
        self._invalidate_motion()
        self.on_state(f"pointer {'ON' if value else 'OFF'}")

    def switch_mode(self) -> None:
        self.mode = "hand" if self.mode == "head" else "head"
        self.mouse.release_all()
        self._left_held = False
        self._invalidate_motion()
        self.on_state(f"mode: {self.mode}")

    def recenter(self) -> None:
        tracker = self._trackers.get("head")
        if tracker is not None and hasattr(tracker, "recenter"):
            tracker.recenter()
        self._invalidate_motion()
        self.on_state("recentered")

    def _invalidate_motion(self) -> None:
        """Drop the motion baseline and resync to the real cursor.

        Called whenever tracking is interrupted. Without this, the first frame
        after a gap produces a delta spanning the entire gap and the cursor
        teleports across the screen.
        """
        self._prev_anchor = None
        self._filter.reset()
        x, y = self.mouse.get_pos()
        self._px, self._py = float(x), float(y)
        self._dwell_anchor = None
        self._need_reanchor = True

    # --- pointer maths --------------------------------------------------
    def control_mode(self) -> str:
        """Resolve "auto" to the right scheme for the current tracking mode.

        A hand has a genuine position in space and plenty of range, so mapping
        it straight onto the screen is both natural and precise -- this is how
        every working hand-mouse behaves. A head does not: its usable range is
        far too small to cover a screen, so it steers relatively instead.
        """
        chosen = self.cfg.pointer.control_mode
        if chosen != "auto":
            return chosen
        return "absolute" if self.mode == "hand" else "relative"

    def _absolute_target(self, fx: float, fy: float) -> tuple[float, float]:
        """Map the anchor through the active region onto the whole screen.

        The active region trims a margin off each edge of the frame before
        mapping. Two reasons: you cannot comfortably reach the corners of the
        camera's view, and tracking quality falls off near the frame edge. So
        a comfortable central rectangle covers the whole screen instead, which
        also means less hand movement per screen inch.
        """
        p = self.cfg.pointer
        mx = min(max(p.active_margin_x, 0.0), 0.45)
        my = min(max(p.active_margin_y, 0.0), 0.45)
        u = (fx - mx) / max(1.0 - 2.0 * mx, 1e-6)
        v = (fy - my) / max(1.0 - 2.0 * my, 1e-6)
        u = min(max(u, 0.0), 1.0)
        v = min(max(v, 0.0), 1.0)
        edge = p.screen_margin
        return (
            self.mouse.origin_x + edge + u * (self.mouse.width - 2 * edge),
            self.mouse.origin_y + edge + v * (self.mouse.height - 2 * edge),
        )

    def _apply_motion(self, sample: Sample, dt: float) -> None:
        p = self.cfg.pointer
        fx, fy = self._filter(sample.ax, sample.ay, dt)
        mode = self.control_mode()

        if mode == "absolute":
            raw_x, raw_y = self._absolute_target(fx, fy)
            if self._need_reanchor:
                # Re-engaging. With the clutch on, bind wherever the hand is
                # now to wherever the cursor already sits, so nothing jumps.
                if p.clutch:
                    self._anchor_offset = (self._px - raw_x, self._py - raw_y)
                else:
                    self._anchor_offset = (0.0, 0.0)
                self._need_reanchor = False
            target_x = raw_x + self._anchor_offset[0]
            target_y = raw_y + self._anchor_offset[1]
            target_x, target_y = self.mouse.clamp(target_x, target_y)
            dx = target_x - self._px
            dy = target_y - self._py
            distance = math.hypot(dx, dy)
            radius = max(p.stabilise_px, 0.0)
            if distance <= radius:
                # Inside the stabiliser: this is jitter, so hold position.
                return
            # Follow only the excess beyond the radius. Subtracting it rather
            # than gating on it keeps movement continuous -- there is no
            # threshold to cross and no jump when you cross it.
            scale = (distance - radius) / distance
            self._px += dx * scale
            self._py += dy * scale
        elif mode == "velocity":
            # Offset from frame centre becomes a speed. The exponent gives a
            # soft zone near the middle so small head movements are gentle.
            ox, oy = fx - 0.5, fy - 0.5
            magnitude = math.hypot(ox, oy)
            if magnitude <= p.velocity_deadzone:
                return
            span = max(0.5 - p.velocity_deadzone, 1e-6)
            t = min((magnitude - p.velocity_deadzone) / span, 1.0)
            speed = p.velocity_max_px_s * (t ** p.velocity_exponent)
            self._px += (ox / magnitude) * speed * dt
            self._py += (oy / magnitude) * speed * dt
        else:  # relative
            if self._prev_anchor is None:
                self._prev_anchor = (fx, fy)
                return
            dx = fx - self._prev_anchor[0]
            dy = fy - self._prev_anchor[1]
            self._prev_anchor = (fx, fy)
            speed = math.hypot(dx, dy) / max(dt, 1e-6)
            gain = accel_gain(
                speed,
                p.deadzone,
                p.speed_knee,
                p.min_gain,
                p.max_gain,
                p.accel_exponent,
            )
            if gain <= 0.0:
                return
            self._px += dx * gain * dt
            self._py += dy * gain * dt

        margin = p.screen_margin
        self._px = min(
            max(self._px, self.mouse.origin_x + margin),
            self.mouse.origin_x + self.mouse.width - 1 - margin,
        )
        self._py = min(
            max(self._py, self.mouse.origin_y + margin),
            self.mouse.origin_y + self.mouse.height - 1 - margin,
        )
        self.mouse.move_to(self._px, self._py)

    def _apply_buttons(self, sample: Sample) -> None:
        now = time.perf_counter()

        if sample.left_down and not self._left_held:
            self.mouse.press("left")
            self._left_held = True
            self._freeze_until = now + self.cfg.pointer.click_freeze_ms / 1000.0
        elif not sample.left_down and self._left_held:
            self.mouse.release("left")
            self._left_held = False
            self._freeze_until = now + self.cfg.pointer.click_freeze_ms / 1000.0

        if sample.right_fire:
            self.mouse.click("right")
            self._freeze_until = now + self.cfg.pointer.click_freeze_ms / 1000.0
        if sample.middle_fire:
            self.mouse.click("middle")

        if sample.scroll:
            self.mouse.scroll(sample.scroll)

    def _apply_dwell(self, sample: Sample) -> str:
        """Click by holding the cursor still. Returns a short status string."""
        head = self.cfg.head
        if self.mode != "head" or head.click_mode != "dwell":
            return ""
        if not sample.ok or sample.parked:
            self._dwell_anchor = None
            return ""

        now = time.perf_counter()
        here = (self._px, self._py)

        if self._dwell_anchor is None:
            self._dwell_anchor = here
            self._dwell_start = now
            self._dwell_armed = True
            return "dwell 0%"

        moved = math.dist(here, self._dwell_anchor)
        if moved > head.dwell_radius_px:
            # Left the zone: restart, and re-arm so the next rest fires again.
            self._dwell_anchor = here
            self._dwell_start = now
            self._dwell_armed = True
            return "dwell 0%"

        elapsed_ms = (now - self._dwell_start) * 1000.0
        if self._dwell_armed and elapsed_ms >= head.dwell_time_ms:
            self.mouse.click("left")
            self._dwell_armed = False
            self._freeze_until = now + self.cfg.pointer.click_freeze_ms / 1000.0
            return "CLICK"
        if not self._dwell_armed:
            return "dwell done - move away to re-arm"
        return f"dwell {min(int(elapsed_ms / head.dwell_time_ms * 100), 99)}%"

    # --- preview --------------------------------------------------------
    # Rows are (label, hint, which debug["gesture"] values light it up).
    _GESTURE_ROWS = (
        ("move", "curl fingers, thumb out", ("move",)),
        ("left click", "pinch thumb + index", ("CLICK",)),
        ("drag", "hold that pinch, move", ("DRAG",)),
        ("right click", "pinch thumb + middle", ("RIGHT",)),
        ("scroll", "I+M up, R down, move", ("SCROLL",)),
        ("park / clutch", "open palm, all spread", ("PARKED",)),
    )

    def _draw_legend(self, sample: Sample) -> None:
        """A cheat sheet that highlights whatever pose is being detected.

        Reading a list of gestures teaches you the names; seeing which line
        lights up as you move your hand teaches you the gestures. The second
        is the one that actually helps, because the usual failure is that the
        pose you are making is not the pose you think you are making.
        """
        width = max(int(self.cfg.preview.width), 160)
        height = max(int(width * 3 / 4), 200)
        card = np.zeros((height, width, 3), np.uint8)
        card[:] = (32, 28, 26)

        detected = str(sample.debug.get("gesture", "")) if sample.ok else ""
        cv2.putText(
            card, "gestures", (8, 20), cv2.FONT_HERSHEY_SIMPLEX,
            0.46, (225, 225, 225), 1, cv2.LINE_AA,
        )

        y = 44
        for label, hint, keys in self._GESTURE_ROWS:
            live = any(k.lower() in detected.lower() for k in keys)
            colour = (90, 230, 120) if live else (165, 165, 165)
            if live:
                cv2.rectangle(card, (4, y - 12), (width - 4, y + 5), (52, 74, 52), -1)
            cv2.putText(
                card, label, (8, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.38, colour, 1, cv2.LINE_AA,
            )
            cv2.putText(
                card, hint, (118, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.32, colour if live else (130, 130, 130), 1, cv2.LINE_AA,
            )
            y += 19

        fingers = str(sample.debug.get("fingers", "no hand seen"))
        cv2.putText(
            card, fingers, (8, height - 26), cv2.FONT_HERSHEY_SIMPLEX,
            0.40, (90, 210, 250), 1, cv2.LINE_AA,
        )
        cv2.putText(
            card, f"{self.cfg.hotkeys.legend} = back to camera", (8, height - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.32, (150, 150, 150), 1, cv2.LINE_AA,
        )
        cv2.imshow(WINDOW, card)

    def _draw(self, frame, sample: Sample, dwell_status: str) -> None:
        if self._show_legend:
            self._draw_legend(sample)
            return

        if self.cfg.camera.mirror:
            frame = cv2.flip(frame, 1)

        # Scale the frame down to the window size *before* drawing, not after.
        # OpenCV scales whatever we hand it to fit the window, so text drawn at
        # 640 px wide and displayed at 360 comes out at 56% size and unreadable.
        # Drawing on the final pixels keeps every label crisp.
        target = max(int(self.cfg.preview.width), 160)
        if frame.shape[1] != target:
            ratio = target / frame.shape[1]
            frame = cv2.resize(
                frame,
                (target, max(int(frame.shape[0] * ratio), 1)),
                interpolation=cv2.INTER_AREA,
            )

        h, w = frame.shape[:2]
        mode = self.control_mode()

        # In absolute mode, draw the active region. Anything inside this box
        # maps to the whole screen, so seeing it is the difference between
        # "the cursor will not move" and "my hand is outside the box".
        if mode == "absolute":
            p = self.cfg.pointer
            mx = int(min(max(p.active_margin_x, 0.0), 0.45) * w)
            my = int(min(max(p.active_margin_y, 0.0), 0.45) * h)
            inside = (
                sample.ok
                and mx <= sample.ax * w <= w - mx
                and my <= sample.ay * h <= h - my
            )
            box = (90, 220, 90) if inside else (90, 90, 220)
            cv2.rectangle(frame, (mx, my), (w - mx, h - my), box, 1)
            cv2.putText(
                frame,
                "active area",
                (mx + 4, my + 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.32,
                box,
                1,
                cv2.LINE_AA,
            )

        state = "ON" if self.enabled else "OFF"
        colour = (80, 220, 80) if self.enabled else (90, 90, 220)
        cv2.rectangle(frame, (0, 0), (w, 24), (30, 30, 30), -1)
        cv2.putText(
            frame,
            f"{state}  {self.mode}/{mode}  {self._fps:.0f}fps",
            (6, 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.44,
            colour,
            1,
            cv2.LINE_AA,
        )

        if sample.ok:
            cx, cy = int(sample.ax * w), int(sample.ay * h)
            cv2.circle(frame, (cx, cy), 7, (0, 215, 255), 2, cv2.LINE_AA)
            cv2.drawMarker(
                frame, (cx, cy), (0, 215, 255), cv2.MARKER_CROSS, 12, 1, cv2.LINE_AA
            )

        lines = [f"{k}: {v}" for k, v in sample.debug.items()]
        if dwell_status:
            lines.append(dwell_status)
        # A small window has limited room; drop anything that would spill over
        # the hotkey hint at the bottom rather than overprinting it.
        room = max((h - 26 - 18) // 15, 1)
        for i, text in enumerate(lines[:room]):
            cv2.putText(
                frame,
                text,
                (6, 40 + i * 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )

        hint = f"{self.cfg.hotkeys.legend}=gestures  {self.cfg.hotkeys.toggle_enable}=off"
        cv2.putText(
            frame,
            hint,
            (6, h - 7),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            (170, 170, 170),
            1,
            cv2.LINE_AA,
        )
        cv2.imshow(WINDOW, frame)

    # --- preview window -------------------------------------------------
    def _open_preview(self, frame_w: int, frame_h: int) -> None:
        """Create the monitor window: small, cornered, and above other apps.

        Topmost matters because the window is useless the moment it is buried
        behind whatever you are actually working in -- you would be aiming your
        hand at a box you cannot see.
        """
        if not self.cfg.show_preview:
            return
        pv = self.cfg.preview
        width = max(int(pv.width), 160)
        height = max(int(width * frame_h / max(frame_w, 1)), 120)

        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW, width, height)
        if pv.topmost:
            try:
                cv2.setWindowProperty(WINDOW, cv2.WND_PROP_TOPMOST, 1)
            except cv2.error:
                pass  # older builds lack the property; the window still works

        # Pump the event loop once so the window really exists, then measure
        # it. Its outer size includes borders and a title bar, which is why
        # placing by the requested image size alone leaves it hanging off the
        # screen edge or tucked under the taskbar.
        cv2.waitKey(1)
        hwnd = find_window(WINDOW)
        outer_w, outer_h = outer_size(hwnd)
        if outer_w <= 0 or outer_h <= 0:
            outer_w, outer_h = width, height

        area_x, area_y, area_w, area_h = work_area()
        margin = max(int(pv.margin_px), 0)
        left = area_x + margin
        top = area_y + margin
        right = area_x + area_w - outer_w - margin
        bottom = area_y + area_h - outer_h - margin
        positions = {
            "top-left": (left, top),
            "top-right": (right, top),
            "bottom-left": (left, bottom),
            "bottom-right": (right, bottom),
        }
        x, y = positions.get(pv.corner, positions["bottom-right"])
        # Never place it off-screen, however odd the numbers come back.
        x = min(max(x, area_x), max(area_x + area_w - outer_w, area_x))
        y = min(max(y, area_y), max(area_y + area_h - outer_h, area_y))
        if not move_window(hwnd, x, y):
            cv2.moveWindow(WINDOW, int(x), int(y))
        self._preview_open = True

    def _close_preview(self) -> None:
        if not self._preview_open:
            return
        try:
            cv2.destroyWindow(WINDOW)
            # OpenCV needs a few event-loop turns to actually tear the window
            # down; without this it can linger as a grey ghost on top.
            for _ in range(4):
                cv2.waitKey(1)
        except cv2.error:
            pass
        self._preview_open = False

    def _splash(self, message: str, sub: str = "") -> None:
        """Paint a status card into the preview window.

        Loading the tracking model takes several seconds on a machine short of
        memory. Without this the sequence is: press hotkey, nothing happens for
        ten seconds, conclude it is broken. Showing the window first and
        reporting progress into it costs nothing and removes that entirely.
        """
        if not self._preview_open:
            return
        width = max(int(self.cfg.preview.width), 160)
        height = max(int(width * 3 / 4), 120)
        card = np.zeros((height, width, 3), np.uint8)
        card[:] = (34, 30, 28)
        cv2.putText(
            card, "MyCursor", (12, 30), cv2.FONT_HERSHEY_SIMPLEX,
            0.58, (210, 210, 210), 1, cv2.LINE_AA,
        )
        cv2.putText(
            card, message, (12, int(height / 2)), cv2.FONT_HERSHEY_SIMPLEX,
            0.44, (90, 210, 250), 1, cv2.LINE_AA,
        )
        if sub:
            cv2.putText(
                card, sub, (12, int(height / 2) + 20), cv2.FONT_HERSHEY_SIMPLEX,
                0.34, (150, 150, 150), 1, cv2.LINE_AA,
            )
        cv2.imshow(WINDOW, card)
        cv2.waitKey(1)

    # --- lifecycle ------------------------------------------------------
    def run(self) -> None:
        """Idle cheaply until woken, track while active, repeat.

        The camera and all inference exist only while active. That is what
        makes it reasonable to leave this running at login: idle costs one
        hotkey poll every few tens of milliseconds, and crucially the webcam
        stays free for Teams, Zoom and anything else.
        """
        toggle = self.cfg.hotkeys.toggle_enable
        try:
            while self.running:
                if self.enabled:
                    self._run_active()
                else:
                    self.on_state("idle - " + toggle + " to start")
                    self._run_idle()
        finally:
            self._teardown()

    def _run_idle(self) -> None:
        delay = max(self.cfg.idle_poll_ms, 5) / 1000.0
        if self.cfg.release_models_when_idle:
            self._release_trackers()
        while self.running and not self.enabled:
            self._handle_keys()
            time.sleep(delay)

    def _run_active(self) -> None:
        cam = self.cfg.camera

        # Window first, work second. The camera and especially the tracking
        # model take seconds to come up on a slow or memory-pressed machine,
        # and the user needs to see that the hotkey did something.
        self._open_preview(cam.width, cam.height)
        self._splash("starting camera...")

        try:
            capture, backend = open_camera(cam.index, cam.width, cam.height, cam.fps)
        except CameraError as exc:
            # Going back to idle is far friendlier than dying: the webcam is
            # usually just busy, and it will be free again in a minute.
            self._splash("camera busy", "another app is using it")
            cv2.waitKey(1200)
            self._close_preview()
            self.on_state("camera unavailable - back to idle")
            print("\n" + str(exc) + "\n", flush=True)
            self.enabled = False
            return

        first_load = self.mode not in self._trackers
        self._splash(
            "loading tracker..." if first_load else "ready",
            "first time takes a few seconds" if first_load else "",
        )
        self._tracker()  # warm up before the first frame so it does not stutter
        self._invalidate_motion()
        self.on_state("active (" + backend + ", " + self.mode + "/" + self.control_mode() + ")")

        last = time.perf_counter()
        misses = 0
        try:
            while self.running and self.enabled:
                ok, frame = capture.read()
                if not ok:
                    misses += 1
                    if misses > 60:
                        self.on_state("camera stopped - back to idle")
                        self.enabled = False
                        break
                    time.sleep(0.01)
                    continue
                misses = 0

                now = time.perf_counter()
                dt = min(max(now - last, 1e-4), 0.25)
                last = now
                self._fps = self._fps * 0.9 + (1.0 / dt) * 0.1

                self._handle_keys()
                if not (self.running and self.enabled):
                    break

                rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                sample = self._tracker().process(rgb, int(now * 1000))

                dwell_status = ""
                if not self.cfg.move_pointer:
                    # Practice mode: track and draw, emit nothing.
                    dwell_status = "practice mode - pointer not moved"
                elif not sample.ok:
                    # Release anything held, and forget the baseline so
                    # re-acquiring does not fling the cursor.
                    if self._left_held:
                        self.mouse.release("left")
                        self._left_held = False
                    self._prev_anchor = None
                    self._need_reanchor = True
                else:
                    frozen = sample.click_disturbance or now < self._freeze_until
                    if sample.parked:
                        self._prev_anchor = None
                        self._need_reanchor = True
                    elif frozen:
                        # Keep the filter fed so it does not jump when the
                        # freeze lifts, but do not move the cursor.
                        fx, fy = self._filter(sample.ax, sample.ay, dt)
                        self._prev_anchor = (fx, fy)
                    else:
                        self._apply_motion(sample, dt)
                    self._apply_buttons(sample)
                    dwell_status = self._apply_dwell(sample)

                if self.cfg.show_preview:
                    self._draw(frame, sample, dwell_status)
                    # waitKey pumps the window and gives us a local 'q'.
                    if (cv2.waitKey(1) & 0xFF) == ord("q"):
                        self.running = False
        finally:
            self.mouse.release_all()
            self._left_held = False
            capture.release()
            self._close_preview()
            self.on_state("camera released")

    def _release_trackers(self) -> None:
        for tracker in self._trackers.values():
            tracker.close()
        self._trackers.clear()

    def _teardown(self) -> None:
        self.mouse.release_all()
        self._close_preview()
        self._release_trackers()

    def _handle_keys(self) -> None:
        fired = self.keys.poll()
        if "quit" in fired:
            self.running = False
            return
        if "toggle" in fired:
            self.set_enabled(not self.enabled)
        if "mode" in fired:
            self.switch_mode()
        if "recenter" in fired:
            self.recenter()
        if "click" in fired:
            self.mouse.click("left")
        if "legend" in fired:
            self._show_legend = not self._show_legend
