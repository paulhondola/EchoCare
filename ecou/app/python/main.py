"""Ecou bring-up test (08-ecou.md §8, step 1).

Runs every part once through the Bridge and prints what it saw, so a wiring or power
problem shows up before any tracking or model work starts. Watch the robot and the
App Lab console together: each step says what should happen.

After the test, Ecou idles: smiling, with the room temperature on the display.
"""

import statistics
import threading
import time

from arduino.app_utils import App, Bridge, Frame

import faces

lock = threading.Lock()
temp_c: float | None = None
temp_ok = 0
temp_failed = 0
dist_samples: list[tuple[float, int]] = []  # (seconds, echo µs)
sweep_points: dict[int, int] = {}  # pan → echo µs
sweep_done = threading.Event()


def log(msg: str) -> None:
    print(msg, flush=True)


def speed_of_sound(celsius: float | None) -> float:
    """Metres per second in air; 20°C when the temperature is not known yet."""
    return 331.3 + 0.606 * (20.0 if celsius is None else celsius)


def echo_to_cm(echo_us: int) -> float | None:
    if echo_us <= 0:
        return None
    return echo_us * speed_of_sound(temp_c) / 20000.0  # there and back, m/s → cm/µs


# --- Notifications from the sketch. These run on the Bridge's thread and must not
# --- call Bridge.call.


def on_temp(ms: int, tenths_c: int, tenths_rh: int, ok: int) -> None:
    global temp_c, temp_ok, temp_failed
    with lock:
        if ok:
            temp_c = tenths_c / 10.0
            temp_ok += 1
        else:
            temp_failed += 1


def on_dist(ms: int, pan: int, tilt: int, echo_us: int) -> None:
    with lock:
        dist_samples.append((time.monotonic(), echo_us))


def on_sweep_pt(seq: int, pan: int, tilt: int, echo_us: int) -> None:
    with lock:
        sweep_points[pan] = echo_us


def on_sweep_end(seq: int) -> None:
    sweep_done.set()


Bridge.provide("temp", on_temp)
Bridge.provide("dist", on_dist)
Bridge.provide("sweep_pt", on_sweep_pt)
Bridge.provide("sweep_end", on_sweep_end)


# --- Helpers


def draw(name_or_array) -> None:
    arr = faces.FACES[name_or_array] if isinstance(name_or_array, str) else name_or_array
    Bridge.call("draw", Frame(arr).to_board_bytes())


def step(title: str, expect: str) -> None:
    log("")
    log(f"=== {title}")
    log(f"    expect: {expect}")


def fmt_cm(cm: float | None) -> str:
    return "  —  " if cm is None else f"{cm:5.1f}"


# --- The test


def test_matrix() -> None:
    step("Matrix", "each face for one second: green, yellow, red, call, cold, hot, asleep")
    for name in faces.FACES:
        log(f"    {name}")
        draw(name)
        time.sleep(1.0)


def test_display() -> None:
    step("Display", "8888, then 1234, then -5°C, then 21°C")
    for kind, value in (("n", 8888), ("n", 1234), ("t", -50), ("t", 214)):
        Bridge.call("show_number" if kind == "n" else "show_temp", value)
        time.sleep(1.0)


def test_temperature() -> None:
    step("Temperature", "at least two good readings in 6 seconds, a plausible room value")
    time.sleep(6.0)
    with lock:
        ok, failed, c = temp_ok, temp_failed, temp_c
    verdict = "OK" if ok >= 2 and c is not None and -10 <= c <= 50 else "CHECK"
    log(f"    [{verdict}] {ok} good, {failed} failed, last {c} °C")
    if verdict != "OK":
        log("    check the data pin, VCC on 3V3, and TEMP_SENSOR in the sketch (DHT11 or DHT22)")
    if c is not None:
        Bridge.call("show_temp", round(c * 10))


def test_servos() -> None:
    step("Neck and arm", "head: centre, left, right, up, down, centre; arm: 0, 90, flag, rest")
    for pan, tilt in ((90, 90), (30, 90), (150, 90), (90, 60), (90, 120), (90, 90)):
        log(f"    look {pan}, {tilt}")
        Bridge.call("look", pan, tilt)
        time.sleep(1.2)
    for deg in (0, 90, 180, 0):
        log(f"    arm {deg}")
        Bridge.call("arm", deg)
        time.sleep(1.0)
    log("    if the board reset during this step, the servos draw from it: use the separate 5 V supply (S17)")

    step("Shiver and fan", "the head trembles for 2 s (cold), then the arm fans for 3 s (hot)")
    draw("cold")
    Bridge.call("shiver", 2000)
    time.sleep(2.5)
    draw("hot")
    Bridge.call("fan", 3000)
    time.sleep(3.5)


def test_distance() -> None:
    step(
        "Eyes, streaming",
        "hold a hand about 20 cm in front of the eyes for 3 s, then take it away for 3 s",
    )
    draw("green")
    with lock:
        dist_samples.clear()
    Bridge.call("look", 90, 90)
    time.sleep(1.0)
    start = time.monotonic()
    Bridge.call("stream", 50)
    time.sleep(6.0)
    Bridge.call("stop")
    with lock:
        samples = list(dist_samples)

    rate = len(samples) / 6.0
    first = [echo_to_cm(e) for t, e in samples if t - start < 3.0]
    second = [echo_to_cm(e) for t, e in samples if t - start >= 3.0]

    def summary(values: list[float | None]) -> str:
        got = [v for v in values if v is not None]
        if not got:
            return "no echo at all"
        return f"median {statistics.median(got):.1f} cm, min {min(got):.1f}, max {max(got):.1f}, {len(values) - len(got)} without echo"

    log(f"    {len(samples)} pings, {rate:.1f} a second (expect about 20)")
    log(f"    hand:    {summary(first)}")
    log(f"    no hand: {summary(second)}")
    if not samples:
        log("    [CHECK] nothing arrived: Trig on D7, Echo on D8 through the divider, VCC on 5V")


def test_sweep() -> None:
    step("Eyes, sweep", "the head turns 0° to 180° in 5° steps, about 3 s, and the room is drawn below")
    with lock:
        sweep_points.clear()
    sweep_done.clear()
    started = time.monotonic()
    Bridge.call("sweep", 0, 180, 5, 90)
    if not sweep_done.wait(timeout=10.0):
        log("    [CHECK] the sweep did not finish in 10 s")
        return
    took = time.monotonic() - started
    with lock:
        points = dict(sweep_points)
    log(f"    {len(points)} steps in {took:.1f} s (expect 37 in about 3 s)")
    for pan in sorted(points):
        cm = echo_to_cm(points[pan])
        bar = "" if cm is None else "#" * min(int(cm / 10), 40)
        log(f"    {pan:3d}° {fmt_cm(cm)} cm {bar}")
    Bridge.call("look", 90, 90)


def test_ask() -> None:
    step("Ask", "„BINE?” scrolls across the matrix while the display counts down from 9")
    frames = list(faces.scroll_frames("BINE?"))
    seconds = 9
    shown = time.monotonic()
    Bridge.call("show_number", seconds)
    while seconds > 0:
        for f in frames:
            draw(f)
            time.sleep(0.08)
            if time.monotonic() - shown >= 1.0:
                seconds -= 1
                shown = time.monotonic()
                Bridge.call("show_number", seconds)
                if seconds == 0:
                    break
    Bridge.call("show_number", -32768)  # blank


def run_test() -> None:
    log("Ecou bring-up test. Watch the robot; each step says what should happen.")
    for test in (test_matrix, test_display, test_temperature, test_servos, test_distance, test_sweep, test_ask):
        try:
            test()
        except Exception as e:  # keep going: one broken part should not hide the others
            log(f"    [ERROR] {type(e).__name__}: {e}")
    log("")
    log("=== Done. Ecou now idles: smiling, room temperature on the display.")
    draw("green")


tested = False


def loop() -> None:
    global tested
    if not tested:
        tested = True
        time.sleep(2.0)  # let the sketch finish starting
        run_test()
        return
    with lock:
        c = temp_c
    if c is not None:
        Bridge.call("show_temp", round(c * 10))
    time.sleep(2.0)


App.run(user_loop=loop)
