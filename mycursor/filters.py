"""Smoothing and gesture-debouncing primitives.

Raw landmark output is far too noisy to drive a cursor directly: a still hand
still jitters by several normalised units per frame, which becomes a visibly
shaking pointer. The One Euro filter is the standard answer because it is
adaptive -- it smooths hard when you are holding still (where jitter is the
enemy) and barely at all when you are moving fast (where lag is the enemy).
A plain moving average cannot do both.
"""

from __future__ import annotations

import math
import time


class LowPass:
    """First-order exponential low-pass with an externally supplied alpha."""

    def __init__(self) -> None:
        self._y: float | None = None

    def reset(self) -> None:
        self._y = None

    def __call__(self, x: float, alpha: float) -> float:
        if self._y is None:
            self._y = x
        else:
            self._y = alpha * x + (1.0 - alpha) * self._y
        return self._y

    @property
    def last(self) -> float | None:
        return self._y


class OneEuro:
    """One Euro filter (Casiez, Roussel & Vogel, CHI 2012), scalar.

    min_cutoff lowers the floor of smoothing when stationary; beta controls
    how aggressively the cutoff opens up as speed rises. Larger beta = more
    responsive to fast movement, at the cost of letting more jitter through.
    """

    def __init__(
        self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0
    ) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x = LowPass()
        self._dx = LowPass()
        self._prev: float | None = None

    def reset(self) -> None:
        self._x.reset()
        self._dx.reset()
        self._prev = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * max(cutoff, 1e-6))
        return 1.0 / (1.0 + tau / max(dt, 1e-6))

    def __call__(self, x: float, dt: float) -> float:
        prev = self._prev if self._prev is not None else x
        speed = (x - prev) / max(dt, 1e-6)
        self._prev = x
        speed_hat = self._dx(speed, self._alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(speed_hat)
        return self._x(x, self._alpha(cutoff, dt))


class OneEuro2D:
    """Two independent One Euro filters, for a point."""

    def __init__(
        self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0
    ) -> None:
        self.x = OneEuro(min_cutoff, beta, d_cutoff)
        self.y = OneEuro(min_cutoff, beta, d_cutoff)

    def retune(self, min_cutoff: float, beta: float, d_cutoff: float) -> None:
        for f in (self.x, self.y):
            f.min_cutoff = min_cutoff
            f.beta = beta
            f.d_cutoff = d_cutoff

    def reset(self) -> None:
        self.x.reset()
        self.y.reset()

    def __call__(self, x: float, y: float, dt: float) -> tuple[float, float]:
        return self.x(x, dt), self.y(y, dt)


class Hysteresis:
    """Schmitt trigger for gesture thresholds.

    A single threshold makes a pinch flicker on and off when your fingers hover
    near it, which fires a burst of clicks. Two thresholds with a gap between
    them make the state sticky, so one pinch is one click.
    """

    def __init__(self, on_below: float, off_above: float, state: bool = False) -> None:
        if on_below >= off_above:
            raise ValueError("on_below must be < off_above to leave a dead band")
        self.on_below = on_below
        self.off_above = off_above
        self.state = state

    def update(self, value: float) -> bool:
        if self.state:
            if value > self.off_above:
                self.state = False
        elif value < self.on_below:
            self.state = True
        return self.state


class RisingEdge:
    """Reports the frame on which a boolean first becomes true."""

    def __init__(self) -> None:
        self._prev = False

    def update(self, value: bool) -> bool:
        fired = value and not self._prev
        self._prev = value
        return fired

    @property
    def held(self) -> bool:
        return self._prev


class Cooldown:
    """Rate limiter, so one intent cannot fire twice in quick succession."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._last = 0.0

    def ready(self) -> bool:
        return (time.perf_counter() - self._last) >= self.seconds

    def stamp(self) -> None:
        self._last = time.perf_counter()

    def try_fire(self) -> bool:
        if self.ready():
            self.stamp()
            return True
        return False


def accel_gain(
    speed: float,
    deadzone: float,
    knee: float,
    min_gain: float,
    max_gain: float,
    exponent: float,
) -> float:
    """Pointer acceleration curve, with a soft knee at the deadzone.

    Between deadzone and `knee` the gain ramps from min to max, so slow
    deliberate movement is precise and a quick flick crosses the screen.

    The subtlety is the final multiplication. A naive curve returns min_gain
    the instant speed exceeds the deadzone, which is a step: one frame the
    cursor is frozen, the next it is moving at min_gain. That step is what
    made the pointer feel like it needed a shove to get going -- there was no
    way to ask for a small movement, only nothing or a jump.

    Scaling by excess/speed removes the step. Gain now rises continuously from
    zero as speed passes the deadzone, so a slow deliberate nudge produces a
    correspondingly small cursor movement, while fast movement is unaffected
    (excess/speed approaches 1). Noise just above the deadzone is attenuated
    instead of being amplified to min_gain.
    """
    if speed <= deadzone:
        return 0.0
    excess = speed - deadzone
    span = max(knee - deadzone, 1e-6)
    t = min(excess / span, 1.0)
    gain = min_gain + (max_gain - min_gain) * (t ** exponent)
    return gain * (excess / speed)


def dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)
