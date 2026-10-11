"""Tune the pointer pipeline against a real recording from your own camera.

Why this exists. Camera-pointer feel is decided by a handful of numbers that
cannot be guessed: the One Euro filter's min_cutoff and beta, and the
acceleration curve's deadzone. Set them wrong one way and a still head
produces a visibly shaking cursor; wrong the other way and the pointer trails
behind you.

How it works. We record a couple of hundred frames of your actual tracking,
then build a reference "truth" signal by smoothing that recording forwards and
then backwards. A double pass like that is zero-phase, so it strips
high-frequency sensor noise without shifting the signal in time, which is
something no live filter can do because a live filter cannot see the future.
Real head motion sits below about 3 Hz while landmark noise is broadband, so
the smoothed version is a good stand-in for what you actually meant to do.

The important part: each candidate is scored by running the *whole* pointer
pipeline -- filter, then acceleration curve, then integration into screen
pixels -- for both the noisy recording and the clean truth, and comparing the
resulting cursor movement. Scoring the filter alone is misleading, because the
acceleration curve is what does most of the noise rejection: it deliberately
gives slow movement a low gain, and sensor noise is small per frame.

  shake  -- screen pixels of cursor movement per frame while you were still.
            This is what you see as a jittering pointer.
  error  -- RMS difference in per-frame cursor movement against the truth,
            while you were actually moving.
  follow -- total cursor travel as a fraction of the truth's. Below 1.0 means
            the pointer feels sluggish; above means it overshoots.

    .\\.venv\\Scripts\\python.exe tools\\tune_filter.py
    .\\.venv\\Scripts\\python.exe tools\\tune_filter.py --mode hand
    .\\.venv\\Scripts\\python.exe tools\\tune_filter.py --apply
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from mycursor.config import Config, PointerConfig
from mycursor.engine import open_camera
from mycursor.filters import OneEuro2D, accel_gain

FRAMES = 240


def record(mode: str, frames: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Capture raw anchor positions. Returns (positions, dts, fps)."""
    cfg = Config()
    if mode == "hand":
        from mycursor.tracker_hand import HandTracker

        tracker = HandTracker(cfg.hand, cfg.camera.mirror)
        prompt = "Hold one hand up. Move it around, then pause, a few times."
    else:
        from mycursor.tracker_head import HeadTracker

        tracker = HeadTracker(cfg.head, cfg.camera.mirror)
        prompt = "Glance to a corner of the screen, pause, glance back. Repeat."

    capture, backend = open_camera(
        cfg.camera.index, cfg.camera.width, cfg.camera.height, cfg.camera.fps
    )
    print(f"camera: {backend}")
    print(f"\n{prompt}")
    print(f"Recording {frames} frames (~{frames / 28:.0f}s). No images are saved.\n")

    for _ in range(10):  # warm-up: first inferences are slow
        ok, frame = capture.read()
        if ok:
            tracker.process(
                np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                int(time.perf_counter() * 1000),
            )

    positions: list[tuple[float, float]] = []
    dts: list[float] = []
    last = time.perf_counter()
    while len(positions) < frames:
        ok, frame = capture.read()
        if not ok:
            continue
        now = time.perf_counter()
        sample = tracker.process(
            np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), int(now * 1000)
        )
        if sample.ok and not sample.parked:
            positions.append((sample.ax, sample.ay))
            dts.append(min(max(now - last, 1e-4), 0.25))
            if len(positions) % 60 == 0:
                print(f"  {len(positions)}/{frames}")
        last = now

    tracker.close()
    capture.release()
    arr_dts = np.array(dts)
    return np.array(positions), arr_dts, float(1.0 / arr_dts.mean())


def zero_phase_truth(series: np.ndarray, alpha: float = 0.18) -> np.ndarray:
    """Smooth forwards then backwards, so there is no time shift."""
    forward = np.empty_like(series)
    acc = series[0].copy()
    for i, value in enumerate(series):
        acc = alpha * value + (1 - alpha) * acc
        forward[i] = acc
    backward = np.empty_like(series)
    acc = forward[-1].copy()
    for i in range(len(forward) - 1, -1, -1):
        acc = alpha * forward[i] + (1 - alpha) * acc
        backward[i] = acc
    return backward


def cursor_steps(
    positions: np.ndarray, dts: np.ndarray, p: PointerConfig, filtered: bool
) -> np.ndarray:
    """Run the engine's relative-mode maths and return per-frame pixel steps.

    Mirrors Engine._apply_motion so that what we tune is what actually runs.
    """
    filt = OneEuro2D(p.filter_min_cutoff, p.filter_beta, p.filter_d_cutoff)
    steps = np.zeros((len(positions), 2))
    previous: tuple[float, float] | None = None

    for i, (point, dt) in enumerate(zip(positions, dts)):
        if filtered:
            fx, fy = filt(point[0], point[1], dt)
        else:
            fx, fy = float(point[0]), float(point[1])
        if previous is None:
            previous = (fx, fy)
            continue
        dx = fx - previous[0]
        dy = fy - previous[1]
        previous = (fx, fy)
        speed = math.hypot(dx, dy) / max(dt, 1e-6)
        gain = accel_gain(
            speed, p.deadzone, p.speed_knee, p.min_gain, p.max_gain, p.accel_exponent
        )
        steps[i] = (dx * gain * dt, dy * gain * dt)
    return steps


def score(
    positions: np.ndarray,
    dts: np.ndarray,
    truth: np.ndarray,
    still: np.ndarray,
    p: PointerConfig,
) -> tuple[float, float, float]:
    test = cursor_steps(positions, dts, p, filtered=True)
    # The truth is already clean, so it needs no live filter -- that is the
    # whole point of the reference.
    ideal = cursor_steps(truth, dts, p, filtered=False)

    test_mag = np.hypot(test[:, 0], test[:, 1])
    ideal_mag = np.hypot(ideal[:, 0], ideal[:, 1])

    shake = float(test_mag[still].mean()) if still.any() else 0.0
    moving = ~still
    if moving.any():
        error = float(
            np.sqrt(((test[moving] - ideal[moving]) ** 2).sum(axis=1).mean())
        )
        travel = float(test_mag[moving].sum())
        ideal_travel = float(ideal_mag[moving].sum())
        follow = travel / ideal_travel if ideal_travel > 1e-9 else 0.0
    else:
        error, follow = 0.0, 0.0
    return shake, error, follow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("head", "hand"), default="head")
    parser.add_argument("--frames", type=int, default=FRAMES)
    parser.add_argument("--shake-budget", type=float, default=0.5,
                        help="max acceptable px of cursor shake per frame while still")
    parser.add_argument("--apply", action="store_true",
                        help="write the best result into settings.json")
    args = parser.parse_args()

    positions, dts, fps = record(args.mode, args.frames)
    if len(positions) < 60:
        print(f"Only captured {len(positions)} samples - not enough to tune.")
        return 1

    truth = zero_phase_truth(positions)
    truth_speed = np.abs(np.diff(truth, axis=0)).sum(axis=1)
    truth_speed = np.append(truth_speed, truth_speed[-1])
    # "Still" = the reference signal's quietest third, where anything we
    # produce is shake rather than intent.
    still = truth_speed <= np.quantile(truth_speed, 0.33)

    base = Config().pointer
    baseline_shake, baseline_error, baseline_follow = score(
        positions, dts, truth, still, base
    )
    print(f"\ncaptured {len(positions)} samples at {fps:.1f} fps")
    print(f"  still frames  {int(still.sum())}/{len(still)}")
    unfiltered = cursor_steps(positions, dts, base, filtered=False)
    print(
        "  with no filter at all: "
        f"{np.hypot(unfiltered[:, 0], unfiltered[:, 1])[still].mean():.2f} px/frame shake"
    )
    print(
        f"  current defaults:      {baseline_shake:.2f} px/frame shake, "
        f"error {baseline_error:.2f} px, follow {baseline_follow:.2f}"
    )

    cutoffs = [0.25, 0.4, 0.6, 0.9, 1.2, 1.8]
    betas = [0.0, 0.02, 0.05, 0.1, 0.3, 0.6, 1.2]
    deadzones = [0.0, 0.05, 0.12, 0.25, 0.5]

    results = []
    for min_cutoff in cutoffs:
        for beta in betas:
            for deadzone in deadzones:
                candidate = PointerConfig(
                    deadzone=deadzone,
                    speed_knee=base.speed_knee,
                    min_gain=base.min_gain,
                    max_gain=base.max_gain,
                    accel_exponent=base.accel_exponent,
                    filter_min_cutoff=min_cutoff,
                    filter_beta=beta,
                    filter_d_cutoff=base.filter_d_cutoff,
                )
                shake, error, follow = score(positions, dts, truth, still, candidate)
                results.append((min_cutoff, beta, deadzone, shake, error, follow))

    # Steadiness first: shake is what makes small targets impossible to hit,
    # whereas a little lag is something you adapt to within minutes. Among the
    # steady-enough candidates, prefer the one that follows the truth best
    # without undershooting badly.
    acceptable = [
        r for r in results if r[3] <= args.shake_budget and 0.75 <= r[5] <= 1.35
    ]
    print(
        f"\nbudget: <= {args.shake_budget} px/frame shake and follow within 0.75-1.35"
    )
    print(f"{len(acceptable)}/{len(results)} candidates qualify\n")

    header = f"{'cutoff':>7} {'beta':>6} {'deadzone':>9} {'shake':>7} {'error':>7} {'follow':>7}"
    print(header)
    print("-" * len(header))

    if acceptable:
        acceptable.sort(key=lambda r: r[4])
        best = acceptable[0]
        for row in acceptable[:10]:
            mark = "  <- best" if row is best else ""
            print(
                f"{row[0]:7.2f} {row[1]:6.2f} {row[2]:9.2f} "
                f"{row[3]:7.2f} {row[4]:7.2f} {row[5]:7.2f}{mark}"
            )
    else:
        results.sort(key=lambda r: r[3])
        best = results[0]
        print("None qualified; steadiest available:")
        for row in results[:10]:
            print(
                f"{row[0]:7.2f} {row[1]:6.2f} {row[2]:9.2f} "
                f"{row[3]:7.2f} {row[4]:7.2f} {row[5]:7.2f}"
            )

    min_cutoff, beta, deadzone, shake, error, follow = best
    print(
        f"\nrecommended for {args.mode} mode:"
        f"\n  filter_min_cutoff = {min_cutoff}"
        f"\n  filter_beta       = {beta}"
        f"\n  deadzone          = {deadzone}"
        f"\n  -> {shake:.2f} px/frame shake while still, "
        f"error {error:.2f} px, follow {follow:.2f}"
    )

    if args.apply:
        cfg = Config.load()
        cfg.pointer.filter_min_cutoff = float(min_cutoff)
        cfg.pointer.filter_beta = float(beta)
        cfg.pointer.deadzone = float(deadzone)
        path = cfg.save()
        print(f"\nwritten to {path}")
    else:
        print("\nre-run with --apply to write these into settings.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
