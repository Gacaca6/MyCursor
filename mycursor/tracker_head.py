"""Head mode: rotation-based pointing with MediaPipe Face Landmarker.

We measure the nose tip's offset from the midpoint of the eyes, divided by the
distance between the eyes. Two useful properties fall out of that:

* Scale invariance. Dividing by the interocular distance means leaning closer
  to or further from the screen does not change the pointer's sensitivity.
* Translation immunity. Shifting your whole head sideways moves the nose and
  the eye midpoint together, so the offset barely changes and the cursor stays
  put. Only *rotating* your head moves the pointer. This is what makes the
  mode survive a full day: you can shift in your chair without the cursor
  wandering off, and you steer with small deliberate turns instead.

Clicking is either dwell (hold still over a target) or facial gesture
(jaw open = left, brows raised = right). Dwell is the default because it needs
nothing from your hands and nothing from your face that a colleague would
notice on a video call.
"""

from __future__ import annotations

from .config import HeadConfig
from .filters import Cooldown, Hysteresis, RisingEdge
from .models import ensure
from .sample import Sample, Tracker

# Landmark indices from the 468-point face mesh.
NOSE_TIP = 1
LEFT_EYE_OUTER = 33
RIGHT_EYE_OUTER = 263

# Blendshape names are ARKit-style; we resolve them by name because the
# index order is not part of MediaPipe's stable API.
JAW_OPEN = "jawOpen"
BROW_INNER_UP = "browInnerUp"


class HeadTracker(Tracker):
    name = "head"

    def __init__(self, cfg: HeadConfig, mirror: bool) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._mp = mp
        self.cfg = cfg
        self.mirror = mirror

        need_blendshapes = cfg.click_mode == "gesture"
        model_path = str(ensure("face_landmarker.task"))
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=need_blendshapes,
            output_facial_transformation_matrixes=False,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

        # Facial gestures get hysteresis for the same reason pinches do: a jaw
        # hovering at the threshold would otherwise fire a stream of clicks.
        # Note the inverted sense -- Hysteresis engages *below* its first
        # argument, so we feed it the negated blendshape score.
        self._jaw = Hysteresis(-cfg.jaw_open_threshold, -cfg.jaw_open_threshold + 0.12)
        self._brow = Hysteresis(
            -cfg.brow_raise_threshold, -cfg.brow_raise_threshold + 0.12
        )
        self._jaw_edge = RisingEdge()
        self._brow_edge = RisingEdge()
        self._gesture_cooldown = Cooldown(cfg.gesture_cooldown_ms / 1000.0)

        # Centre of the comfortable head range. Recalibrated on demand so the
        # neutral position is wherever you are actually sitting.
        self._origin: tuple[float, float] | None = None
        self._recenter_requested = True
        self._last_ts = 0

    def recenter(self) -> None:
        """Treat the current head pose as pointing at the screen centre."""
        self._recenter_requested = True

    # --- helpers -------------------------------------------------------
    @staticmethod
    def _blendshape(result, name: str) -> float:
        if not result.face_blendshapes:
            return 0.0
        for category in result.face_blendshapes[0]:
            if category.category_name == name:
                return float(category.score)
        return 0.0

    # --- main ----------------------------------------------------------
    def process(self, rgb, timestamp_ms: int) -> Sample:
        if timestamp_ms <= self._last_ts:
            timestamp_ms = self._last_ts + 1
        self._last_ts = timestamp_ms

        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, timestamp_ms)

        if not result.face_landmarks:
            return self._lost()

        lm = result.face_landmarks[0]
        nose = lm[NOSE_TIP]
        left = lm[LEFT_EYE_OUTER]
        right = lm[RIGHT_EYE_OUTER]

        eye_cx = (left.x + right.x) / 2.0
        eye_cy = (left.y + right.y) / 2.0
        # Interocular distance is our scale reference. Guard the divide: a
        # face turned almost fully side-on collapses it toward zero.
        span = max(abs(right.x - left.x), 1e-3)

        offset_x = (nose.x - eye_cx) / span
        offset_y = (nose.y - eye_cy) / span

        if self.mirror:
            offset_x = -offset_x

        if self._recenter_requested or self._origin is None:
            self._origin = (offset_x, offset_y)
            self._recenter_requested = False

        # Map the offset into a 0..1 anchor around frame centre. The divisor
        # sets how far you must turn your head to cross the whole screen;
        # sensitivity scales it.
        ax = 0.5 + (offset_x - self._origin[0]) * self.cfg.sensitivity_x * 2.2
        ay = 0.5 + (offset_y - self._origin[1]) * self.cfg.sensitivity_y * 2.2

        sample = Sample(ok=True, ax=ax, ay=ay)
        debug: dict[str, object] = {
            "off_x": round(offset_x - self._origin[0], 3),
            "off_y": round(offset_y - self._origin[1], 3),
        }

        if self.cfg.click_mode == "gesture":
            jaw_score = self._blendshape(result, JAW_OPEN)
            brow_score = self._blendshape(result, BROW_INNER_UP)
            jaw_on = self._jaw.update(-jaw_score)
            brow_on = self._brow.update(-brow_score)

            if self._brow_edge.update(brow_on) and self._gesture_cooldown.try_fire():
                sample.right_fire = True
            elif jaw_on and self._gesture_cooldown.ready():
                sample.left_down = True
            self._jaw_edge.update(jaw_on)

            # Opening your jaw tugs the whole lower face, which shifts the
            # nose a little. Freeze while a gesture is active.
            sample.click_disturbance = jaw_on or brow_on
            debug["jaw"] = round(jaw_score, 2)
            debug["brow"] = round(brow_score, 2)
            debug["gesture"] = "jaw" if jaw_on else ("brow" if brow_on else "move")
        else:
            # Dwell is handled by the engine, which is the only thing that
            # knows where the cursor actually ended up on screen.
            debug["gesture"] = self.cfg.click_mode

        sample.debug = debug
        return sample

    def _lost(self) -> Sample:
        self._jaw.state = False
        self._brow.state = False
        self._jaw_edge.update(False)
        self._brow_edge.update(False)
        return Sample(ok=False, parked=True, debug={"gesture": "no face"})

    def reset(self) -> None:
        self._lost()
        self._recenter_requested = True

    def close(self) -> None:
        self._landmarker.close()
