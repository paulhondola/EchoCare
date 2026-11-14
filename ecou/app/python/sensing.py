"""Ecou's signal processing (08-ecou.md §2.2–§2.5). Pure functions and small classes,
no Bridge and no hardware, so they are tested on a laptop (ecou/tests).

Distances are in metres, angles in degrees (0 is the robot's right, 90 straight ahead,
180 its left), times in seconds.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field

MAX_RANGE_M = 4.0  # HC-SR04 gives up beyond this


def speed_of_sound(celsius: float | None) -> float:
    """Metres per second in air; 20°C when the room is not known yet."""
    return 331.3 + 0.606 * (20.0 if celsius is None else celsius)


def echo_to_m(echo_us: int, celsius: float | None = None) -> float | None:
    """The distance an echo time stands for, there and back; None for no echo or one
    beyond the sensor's range."""
    if echo_us <= 0:
        return None
    metres = echo_us * 1e-6 * speed_of_sound(celsius) / 2
    return metres if metres <= MAX_RANGE_M else None


def or_far(metres: float | None) -> float:
    """No echo reads as the far end of the range, so arithmetic still works."""
    return MAX_RANGE_M if metres is None else metres


# ---------------------------------------------------------------------------------
# Baseline: the empty room, one slowly learned distance per angle (§2.2, §2.4)


@dataclass
class Baseline:
    """The room without people, per angle step. A new angle takes its first reading;
    afterwards each reading moves the value a little, so a moved chair stops counting
    after a while, but a person passing does not become furniture."""

    rate: float = 0.05
    values: dict[int, float] = field(default_factory=dict)

    def learn(self, angle: int, metres: float | None) -> None:
        d = or_far(metres)
        old = self.values.get(angle)
        self.values[angle] = d if old is None else old + self.rate * (d - old)

    def get(self, angle: int) -> float | None:
        return self.values.get(angle)

    def ready(self, angles: list[int]) -> bool:
        return all(a in self.values for a in angles)


def candidates(
    sweep: dict[int, float | None], baseline: Baseline, margin: float = 0.3
) -> list[tuple[int, float]]:
    """Angles where something is nearer than the empty room by `margin`, with their
    distance: whatever is new in the room."""
    found = []
    for angle, metres in sorted(sweep.items()):
        base = baseline.get(angle)
        if metres is not None and base is not None and metres < base - margin:
            found.append((angle, metres))
    return found


# ---------------------------------------------------------------------------------
# Tracker: one target, a constant-velocity Kalman filter on angle and distance (§2.2)


class Kalman1D:
    """Position and velocity of one coordinate under a constant-velocity model."""

    def __init__(self, x: float, q: float, r: float) -> None:
        self.x = [x, 0.0]
        self.p = [[r, 0.0], [0.0, 10.0 * r]]
        self.q, self.r = q, r

    def predict(self, dt: float) -> float:
        x, v = self.x
        self.x = [x + v * dt, v]
        (a, b), (c, d) = self.p
        # P = F P F' + Q, with F = [[1, dt], [0, 1]]
        a, b, c, d = (
            a + dt * (b + c) + dt * dt * d,
            b + dt * d,
            c + dt * d,
            d,
        )
        q = self.q
        self.p = [
            [a + q * dt**3 / 3, b + q * dt**2 / 2],
            [c + q * dt**2 / 2, d + q * dt],
        ]
        return self.x[0]

    def update(self, z: float) -> float:
        (a, b), (c, d) = self.p
        s = a + self.r
        k0, k1 = a / s, c / s
        y = z - self.x[0]
        self.x = [self.x[0] + k0 * y, self.x[1] + k1 * y]
        self.p = [[(1 - k0) * a, (1 - k0) * b], [c - k1 * a, d - k1 * b]]
        return self.x[0]


@dataclass
class Track:
    angle: float
    distance: float
    last_seen: float
    moved_at: float


class Tracker:
    """Follows the one person Ecou looks at. A measurement too far from the prediction
    is someone else, and is ignored; a track not confirmed for `lose_after` is lost."""

    def __init__(self, lose_after: float = 2.5, gate_deg: float = 25.0) -> None:
        self.lose_after = lose_after
        self.gate_deg = gate_deg
        self.track: Track | None = None
        self._angle: Kalman1D | None = None
        self._dist: Kalman1D | None = None
        self._t = 0.0

    def predicted_angle(self, now: float) -> float | None:
        if self.track is None or self._angle is None:
            return None
        x, v = self._angle.x
        return max(0.0, min(180.0, x + v * (now - self._t)))

    def update(self, now: float, found: list[tuple[int, float]]) -> Track | None:
        """Feeds one sweep's candidates; returns the track, or None when there is none."""
        if self.track is not None and now - self.track.last_seen > self.lose_after:
            self.track = None
        if not found:
            return self.track
        if self.track is None:
            angle, dist = min(found, key=lambda c: c[1])  # the nearest new thing
            self._angle = Kalman1D(angle, q=400.0, r=25.0)
            self._dist = Kalman1D(dist, q=1.0, r=0.01)
            self._t = now
            self.track = Track(angle, dist, now, now)
            return self.track
        dt = max(now - self._t, 1e-3)
        guess = self._angle.predict(dt)
        self._dist.predict(dt)
        self._t = now
        angle, dist = min(found, key=lambda c: abs(c[0] - guess))
        if abs(angle - guess) > self.gate_deg:
            return self.track
        new_angle = self._angle.update(angle)
        new_dist = self._dist.update(dist)
        moved = abs(new_angle - self.track.angle) > 4 or abs(new_dist - self.track.distance) > 0.1
        self.track = Track(new_angle, new_dist, now, now if moved else self.track.moved_at)
        return self.track


# ---------------------------------------------------------------------------------
# Gestures (§2.3): rules first; a trained model may replace `classify` later

NEAR_M = 0.45


def classify(window: list[float | None], rate_hz: float = 20.0) -> str:
    """One of `wave`, `palm`, `pass`, `none` for a window of distances straight ahead.

    - palm: something held within NEAR_M, steady to 2 cm, for the whole window.
    - wave: the hand comes and goes at least four times.
    - pass: one dip, someone walking by.
    """
    if len(window) < rate_hz:  # under a second tells nothing
        return "none"
    near = [d is not None and d < NEAR_M for d in window]
    share = sum(near) / len(window)
    flips = sum(1 for a, b in zip(near, near[1:], strict=False) if a != b)
    if share >= 0.9:
        held = [d for d in window if d is not None and d < NEAR_M]
        if statistics.pstdev(held) < 0.02:
            return "palm"
    if flips >= 4:
        return "wave"
    if 0.05 <= share <= 0.7 and flips <= 2:
        return "pass"
    return "none"


# ---------------------------------------------------------------------------------
# Floor search (§2.4)


@dataclass
class Lying:
    angle: float
    distance: float
    width_steps: int


def find_lying(
    sweep: dict[int, float | None],
    floor: Baseline,
    margin: float = 0.15,
    min_steps: int = 3,
) -> Lying | None:
    """The widest run of neighbouring steps nearer than the floor by `margin`: something
    lying where the floor was. At least `min_steps` wide (15° at 5° steps)."""
    angles = sorted(sweep)
    best: list[int] = []
    run: list[int] = []
    for angle in angles:
        metres, base = sweep[angle], floor.get(angle)
        if metres is not None and base is not None and metres < base - margin:
            run.append(angle)
        else:
            best = run if len(run) > len(best) else best
            run = []
    best = run if len(run) > len(best) else best
    if len(best) < min_steps:
        return None
    distances = [sweep[a] for a in best]
    return Lying(
        angle=statistics.fmean(best),
        distance=statistics.median(d for d in distances if d is not None),
        width_steps=len(best),
    )


class LyingWatch:
    """Something found lying counts once it stays in the same place, within
    `tolerance_deg`, for `hold` seconds across sweeps."""

    def __init__(self, hold: float, tolerance_deg: float = 15.0) -> None:
        self.hold = hold
        self.tolerance = tolerance_deg
        self.since: float | None = None
        self.where: Lying | None = None

    def update(self, now: float, found: Lying | None) -> Lying | None:
        if found is None:
            self.since, self.where = None, None
            return None
        if self.where is None or abs(found.angle - self.where.angle) > self.tolerance:
            self.since, self.where = now, found
            return None
        self.where = found
        since = now if self.since is None else self.since
        return found if now - since >= self.hold else None


# ---------------------------------------------------------------------------------
# Room temperature forecast (§2.5)


@dataclass
class Forecast:
    window_s: float = 1800.0  # fit the last 30 minutes
    min_span_s: float = 600.0  # and only with at least 10 minutes of readings
    readings: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=2000))

    def add(self, t: float, celsius: float) -> None:
        self.readings.append((t, celsius))
        while self.readings and t - self.readings[0][0] > self.window_s:
            self.readings.popleft()

    def predict(self, ahead_s: float = 3600.0) -> float | None:
        """The temperature `ahead_s` from the last reading: Newton's cooling,
        T(t) = T∞ + (T0 − T∞)·e^(−t/τ), fitted by trying τ and solving the rest by least
        squares; a straight line when the curve does not fit better. None without
        enough readings."""
        if len(self.readings) < 5:
            return None
        t0 = self.readings[0][0]
        ts = [t - t0 for t, _ in self.readings]
        ys = [c for _, c in self.readings]
        if ts[-1] < self.min_span_s:
            return None
        horizon = ts[-1] + ahead_s

        line = linear_fit(ts, ys)
        best = (line[2], line[0] + line[1] * horizon)
        for tau in (300, 600, 900, 1200, 1800, 2700, 3600, 5400, 7200, 10800):
            fit = exponential_fit(ts, ys, tau)
            if fit is None:
                continue
            t_inf, amp, err = fit
            if err < best[0] * 0.9:  # the curve must earn its extra freedom
                best = (err, t_inf + amp * math.exp(-horizon / tau))
        return round(best[1], 1)


def linear_fit(ts: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Intercept, slope and the sum of squared errors."""
    n = len(ts)
    mt, my = sum(ts) / n, sum(ys) / n
    var = sum((t - mt) ** 2 for t in ts)
    slope = 0.0 if var == 0 else sum((t - mt) * (y - my) for t, y in zip(ts, ys, strict=True)) / var
    icept = my - slope * mt
    err = sum((icept + slope * t - y) ** 2 for t, y in zip(ts, ys, strict=True))
    return icept, slope, err


def exponential_fit(
    ts: list[float], ys: list[float], tau: float
) -> tuple[float, float, float] | None:
    """For a fixed τ the model is linear in T∞ and the amplitude: y = T∞ + A·e^(−t/τ)."""
    xs = [math.exp(-t / tau) for t in ts]
    icept, slope, err = linear_fit(xs, ys)
    if not math.isfinite(err):
        return None
    return icept, slope, err


# ---------------------------------------------------------------------------------


def side_of(angle: float) -> str:
    """Where an angle is, from the robot's side of the room, in Romanian."""
    if angle > 112.5:
        return "în stânga"
    if angle < 67.5:
        return "în dreapta"
    return "în față"
