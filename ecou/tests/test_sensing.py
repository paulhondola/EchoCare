"""ecou/app/python/sensing.py: the parts of Ecou that need no board (08-ecou.md §2)."""

import math
import random

import pytest
from sensing import (
    Baseline,
    Forecast,
    LyingWatch,
    Tracker,
    candidates,
    classify,
    echo_to_m,
    find_lying,
    side_of,
)


def test_echo_to_metres_follows_the_temperature():
    # 5831 µs is 1 m there and back at 20°C (343.4 m/s)
    assert echo_to_m(5831, 20.0) == pytest.approx(1.0, abs=0.005)
    assert echo_to_m(5831, 0.0) < echo_to_m(5831, 30.0)
    assert echo_to_m(0) is None
    assert echo_to_m(30000) is None  # beyond the sensor's 4 m


def room(distance=3.0) -> dict[int, float]:
    return {a: distance for a in range(0, 181, 5)}


def learned(sweep) -> Baseline:
    b = Baseline()
    for a, m in sweep.items():
        b.learn(a, m)
    return b


def test_a_person_is_what_is_nearer_than_the_room():
    base = learned(room())
    now = room() | {85: 1.5, 90: 1.4}
    assert candidates(now, base) == [(85, 1.5), (90, 1.4)]
    assert candidates(room(2.9), base) == []  # within the margin


def test_the_baseline_forgets_a_moved_chair_slowly():
    base = learned(room())
    base.learn(90, 1.0)
    assert base.get(90) > 2.8  # one sighting barely moves it
    for _ in range(200):
        base.learn(90, 1.0)
    assert base.get(90) == pytest.approx(1.0, abs=0.01)


def test_the_tracker_follows_and_ignores_someone_else():
    t = Tracker()
    track = t.update(0.0, [(60, 2.0)])
    assert track.angle == 60
    for i in range(1, 8):  # walking to the left, 5° every half second
        track = t.update(i * 0.5, [(60 + 5 * i, 2.0), (150, 1.0)])
    assert 85 <= track.angle <= 100
    assert t.predicted_angle(4.0) > track.angle - 1


def test_the_tracker_loses_a_target_it_no_longer_sees():
    t = Tracker(lose_after=2.0)
    t.update(0.0, [(90, 2.0)])
    assert t.update(3.0, []) is None


def window(values):
    return list(values)


def test_a_still_palm():
    assert classify([0.25 + random.uniform(-0.005, 0.005) for _ in range(40)]) == "palm"


def test_a_wave():
    # the hand comes and goes: 5 near, 5 far, four times
    assert classify(([0.25] * 5 + [None] * 5) * 4) == "wave"


def test_someone_walking_past():
    assert classify([None] * 15 + [0.4] * 8 + [None] * 17) == "pass"


def test_nothing_in_front():
    assert classify([None] * 40) == "none"
    assert classify([2.5] * 40) == "none"
    assert classify([0.25] * 10) == "none"  # too short to tell


def test_something_lying_is_a_wide_run_nearer_than_the_floor():
    floor = learned(room(2.5))
    sweep = room(2.5) | {100: 2.1, 105: 2.0, 110: 2.1, 115: 2.2}
    lying = find_lying(sweep, floor)
    assert lying.width_steps == 4
    assert lying.angle == pytest.approx(107.5)
    assert lying.distance == pytest.approx(2.1)
    assert side_of(lying.angle) == "în față"


def test_a_narrow_thing_is_not_lying():
    floor = learned(room(2.5))
    assert find_lying(room(2.5) | {100: 2.0, 105: 2.0}, floor) is None  # a chair leg


def test_lying_counts_once_it_stays_put():
    floor = learned(room(2.5))
    sweep = room(2.5) | {a: 2.0 for a in (40, 45, 50)}
    watch = LyingWatch(hold=8.0)
    assert watch.update(0.0, find_lying(sweep, floor)) is None
    assert watch.update(5.0, find_lying(sweep, floor)) is None
    assert watch.update(9.0, find_lying(sweep, floor)) is not None
    assert watch.update(10.0, None) is None  # gone: start again
    assert side_of(45) == "în dreapta"


def test_the_forecast_follows_newtons_cooling():
    # A room at 21°C cooling towards 8°C outside with τ = 40 minutes
    f = Forecast()
    for i in range(0, 31):
        t = i * 60.0
        f.add(t, 8 + 13 * math.exp(-t / 2400))
    predicted = f.predict(3600)
    truth = 8 + 13 * math.exp(-(1800 + 3600) / 2400)
    assert predicted == pytest.approx(truth, abs=1.0)
    assert predicted < 16  # below the cold limit: cold_soon


def test_the_forecast_waits_for_enough_readings():
    f = Forecast()
    for i in range(5):
        f.add(i * 60.0, 21.0)
    assert f.predict() is None  # four minutes is too little


def test_a_steady_room_stays_steady():
    f = Forecast()
    for i in range(31):
        f.add(i * 60.0, 21.0 + random.uniform(-0.1, 0.1))
    assert f.predict() == pytest.approx(21.0, abs=0.5)
