"""End-to-end check: models load, camera runs, trackers produce samples.

Reports aggregate statistics only. No frames are written to disk and nothing
leaves the machine. The mouse is never touched, so this is safe to run at any
time to confirm the pipeline still works.

    .\\.venv\\Scripts\\python.exe tools\\smoke_test.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from mycursor.config import Config
from mycursor.engine import open_camera
from mycursor.models import ensure

FRAMES = 60


def check_models() -> bool:
    print("1. models")
    ok = True
    for name in ("hand_landmarker.task", "face_landmarker.task"):
        try:
            path = ensure(name)
            print(f"   OK   {name}  ({path.stat().st_size // 1024} KB)")
        except Exception as exc:
            print(f"   FAIL {name}: {exc}")
            ok = False
    return ok


def run_tracker(label: str, tracker, capture, frames: int = FRAMES) -> bool:
    detected = 0
    anchors: list[tuple[float, float]] = []
    started = time.perf_counter()

    for i in range(frames):
        ok, frame = capture.read()
        if not ok:
            continue
        rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        sample = tracker.process(rgb, int(time.perf_counter() * 1000))
        if sample.ok:
            detected += 1
            anchors.append((sample.ax, sample.ay))

    elapsed = time.perf_counter() - started
    fps = frames / elapsed if elapsed else 0.0
    rate = detected / frames * 100 if frames else 0.0

    print(f"   frames      {frames} in {elapsed:.1f}s  ({fps:.1f} fps)")
    print(f"   detected    {detected}/{frames}  ({rate:.0f}%)")

    if anchors:
        xs = [a[0] for a in anchors]
        ys = [a[1] for a in anchors]
        print(f"   anchor x    {min(xs):.3f} .. {max(xs):.3f}")
        print(f"   anchor y    {min(ys):.3f} .. {max(ys):.3f}")
        # Landmarks live in 0..1; anything outside means a mapping bug.
        in_range = all(-0.5 <= v <= 1.5 for v in xs + ys)
        print(f"   in range    {'OK' if in_range else 'FAIL - anchor out of bounds'}")
        jitter = 0.0
        if len(anchors) > 1:
            jitter = float(
                np.mean(
                    [
                        abs(anchors[i][0] - anchors[i - 1][0])
                        + abs(anchors[i][1] - anchors[i - 1][1])
                        for i in range(1, len(anchors))
                    ]
                )
            )
        print(f"   raw jitter  {jitter:.4f} units/frame (unfiltered)")
        return in_range

    print(f"   nothing detected - was a {label} visible to the camera?")
    return True  # not a code failure; the subject may simply be absent


def main() -> int:
    print("MyCursor smoke test")
    print("(the webcam turns on briefly; no images are saved or sent)\n")

    cfg = Config()
    if not check_models():
        return 1

    print("\n2. camera")
    try:
        capture, backend = open_camera(
            cfg.camera.index, cfg.camera.width, cfg.camera.height, cfg.camera.fps
        )
    except Exception as exc:
        print(f"   FAIL {exc}")
        return 2
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"   OK   {backend} backend, {width}x{height}")

    results = {}
    try:
        print("\n3. head tracker  (look at the screen)")
        from mycursor.tracker_head import HeadTracker

        head = HeadTracker(cfg.head, cfg.camera.mirror)
        results["head"] = run_tracker("face", head, capture)
        head.close()

        print("\n4. hand tracker  (hold a hand up if you can)")
        from mycursor.tracker_hand import HandTracker

        hand = HandTracker(cfg.hand, cfg.camera.mirror)
        results["hand"] = run_tracker("hand", hand, capture)
        hand.close()
    finally:
        capture.release()

    print("\n5. mouse driver  (geometry only, pointer not moved)")
    from mycursor.input_win import MouseDriver

    driver = MouseDriver()
    print(
        f"   OK   virtual desktop {driver.width}x{driver.height} "
        f"at ({driver.origin_x},{driver.origin_y}), cursor at {driver.get_pos()}"
    )

    failed = [k for k, v in results.items() if not v]
    print("\n" + ("FAILED: " + ", ".join(failed) if failed else "All checks passed."))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
