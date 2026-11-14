"""Ecou bring-up test (08-ecou.md §8, step 1).

Runs every part once and prints what it saw, so a wiring or power problem shows up
before any tracking or model work starts. Watch the robot and the App Lab console
together: each step says what should happen.
"""

from __future__ import annotations

import statistics
import time

import faces
from body import Body


def log(msg: str) -> None:
    print(msg, flush=True)


def step(title: str, expect: str) -> None:
    log("")
    log(f"=== {title}")
    log(f"    expect: {expect}")


def test_matrix(body: Body) -> None:
    step("Matrix", "each face for one second: " + ", ".join(faces.FACES))
    for name in faces.FACES:
        log(f"    {name}")
        body.face(name)
        time.sleep(1.0)


def test_display(body: Body) -> None:
    step("Display", "8888, then 1234, then -5°C, then 21°C")
    body.show_number(8888)
    time.sleep(1.0)
    body.show_number(1234)
    time.sleep(1.0)
    body.show_temp(-5.0)
    time.sleep(1.0)
    body.show_temp(21.4)
    time.sleep(1.0)


def test_temperature(body: Body) -> None:
    step("Temperature", "at least two good readings in 6 seconds, a plausible room value")
    time.sleep(6.0)
    c = body.temp_c
    verdict = "OK" if body.temp_ok >= 2 and c is not None and -10 <= c <= 50 else "CHECK"
    log(f"    [{verdict}] {body.temp_ok} good, {body.temp_failed} failed, last {c} °C")
    if verdict != "OK":
        log("    check the data pin (D4), VCC on 3V3, and TEMP_SENSOR in the sketch")
    if c is not None:
        body.show_temp(c)


def test_servos(body: Body) -> None:
    step("Neck", "head: centre, right, left, up, down, centre")
    for pan, tilt in ((90, 90), (30, 90), (150, 90), (90, 60), (90, 120), (90, 90)):
        log(f"    look {pan}, {tilt}")
        body.look(pan, tilt)
        time.sleep(1.2)
    log("    if the board reset during this step, the servos need their own 5 V (S17)")

    step("Shiver", "the head trembles for 2 s (cold)")
    body.face("cold")
    body.shiver(2000)
    time.sleep(2.5)


def test_distance(body: Body) -> None:
    step(
        "Eyes, streaming",
        "hold a hand about 20 cm in front of the eyes for 3 s, then take it away for 3 s",
    )
    body.face("green")
    body.look(90, 90)
    time.sleep(1.0)
    first = body.stream(3.0)
    second = body.stream(3.0)

    def summary(values: list[float | None]) -> str:
        got = [v * 100 for v in values if v is not None]
        if not got:
            return "no echo at all"
        return (
            f"median {statistics.median(got):.1f} cm, min {min(got):.1f}, "
            f"max {max(got):.1f}, {len(values) - len(got)} without echo"
        )

    log(f"    {len(first) + len(second)} pings in 6 s (expect about 120)")
    log(f"    hand:    {summary(first)}")
    log(f"    no hand: {summary(second)}")
    if not first and not second:
        log("    [CHECK] nothing arrived: Trig on D7, Echo on D8 through the divider, VCC on 5V")


def test_sweep(body: Body) -> None:
    step(
        "Eyes, sweep",
        "the head turns 0° to 180° in 5° steps, about 3 s, and the room is drawn below",
    )
    started = time.monotonic()
    points = body.sweep(0, 180, 5, 90)
    took = time.monotonic() - started
    log(f"    {len(points)} steps in {took:.1f} s (expect 37 in about 3 s)")
    for pan in sorted(points):
        m = points[pan]
        shown = "  —  " if m is None else f"{m * 100:5.1f}"
        bar = "" if m is None else "#" * min(int(m * 10), 40)
        log(f"    {pan:3d}° {shown} cm {bar}")
    body.look(90, 90)


def test_ask(body: Body) -> None:
    step("Ask", "„BINE?” scrolls across the matrix while the display counts down from 9")
    frames = list(faces.scroll_frames("BINE?"))
    end = time.monotonic() + 9.0
    i = 0
    while (left := end - time.monotonic()) > 0:
        body.show_number(int(left) + 1)
        body.draw(frames[i % len(frames)])
        i += 1
        time.sleep(0.08)
    body.blank()


def run(body: Body) -> None:
    log("Ecou bring-up test. Watch the robot; each step says what should happen.")
    for test in (
        test_matrix,
        test_display,
        test_temperature,
        test_servos,
        test_distance,
        test_sweep,
        test_ask,
    ):
        try:
            test(body)
        except Exception as e:  # keep going: one broken part should not hide the others
            log(f"    [ERROR] {type(e).__name__}: {e}")
    log("")
    log("=== Done. Ecou now idles: smiling, room temperature on the display.")
    body.face("green")
