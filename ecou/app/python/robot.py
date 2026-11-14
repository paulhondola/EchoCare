"""Ecou, the robot (08-ecou.md §2): the mode machine that ties the eyes, the neck, the
face and the phone together.

    Look    follow the nearest moving person; read gestures when a hand comes close
    Search  nobody seen for a while: tilt down and sweep the floor
    Ask     something lying still: „BINE?”, a countdown, a wave cancels
    Quiet   at night: head still, a floor sweep now and then

Ecou decides nothing about codes. It tells the phone what it saw (room readings,
motion, SOS, a fall) and shows what the phone writes back (the code, the room state).
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import faces
from body import Body
from node_ble import NodeServer
from puiul_link import PuiulLink
from sensing import (
    Baseline,
    Forecast,
    LyingWatch,
    Tracker,
    candidates,
    classify,
    find_lying,
    or_far,
    side_of,
)

# --- configuration ------------------------------------------------------------------

DEMO = os.environ.get("ECOU_DEMO", "1") != "0"  # demo timers (06 §3, 08-ecou.md §5)
NAME = os.environ.get("ECOU_NAME", "Ecou")
HAS_TILT = True  # False for the one-servo build (08-ecou.md §1.1)
TILT_LEVEL = 90  # the tilt at which the eyes look straight ahead
# The tilt at which the beam meets the floor 1.5–2.5 m away. Depends on how the tilt
# servo is mounted: set it once on the shelf, with the bring-up test's look().
TILT_FLOOR = 120 if HAS_TILT else TILT_LEVEL
STEP = 5  # degrees between pings in a sweep
WINDOW = 15  # half-width of the tracking window, degrees
BUCHAREST = ZoneInfo("Europe/Bucharest")

READING_EVERY = 5.0 if DEMO else 60.0  # room reading to the phone (06 §3)
SEARCH_AFTER = 10.0 if DEMO else 120.0  # nobody seen for this long: search
LYING_HOLD = 8.0 if DEMO else 30.0
ASK_TIMEOUT = 15.0 if DEMO else 30.0
QUIET_SWEEP_EVERY = 600.0
PALM_HOLD = 3.0  # seconds of a still palm for an SOS (P25)
FORECAST = (
    Forecast(window_s=180.0, min_span_s=45.0) if DEMO else Forecast()
)  # in the demo an ice pack moves the fit within a minute


def log(msg: str) -> None:
    print(f"[ecou] {msg}", flush=True)


class Ecou:
    def __init__(self, body: Body) -> None:
        self.body = body
        self.mode = "look"
        self.started = time.monotonic()
        self.tracker = Tracker()
        self.room = Baseline()
        self.floor = Baseline()
        self.lying = LyingWatch(hold=LYING_HOLD)
        self.forecast = FORECAST
        self.last_seen = time.monotonic()
        self.last_motion = time.monotonic()
        self.last_motion_sent = 0.0
        self.last_reading = 0.0
        self.last_body = 0.0
        self.last_quiet_sweep = 0.0
        self.code = "green"  # the Light characteristic: green, yellow, red, call
        self.room_state = "ok"  # the Room state characteristic (P26)
        self.palm_since: float | None = None
        self.asking: dict | None = None
        body.on_temperature(lambda t, c: self.forecast.add(t, c))

        self.ble = NodeServer(NAME, self._on_light, self._on_room_state, self._on_ack)
        self.phone_ok = self.ble.start()
        if not self.phone_ok:
            log("no BLE: running without a phone (S14 fallback in 08-ecou.md §6)")
        self.puiul = PuiulLink(self._on_kitchen_pass, self._on_kitchen_sos)
        self.puiul.start()

    # --- from the phone and from Puiul (other threads) ---------------------------

    def _on_light(self, value: str) -> None:
        if value in ("green", "yellow", "red", "call"):
            self.code = value
            self.puiul.code = value

    def _on_room_state(self, value: str) -> None:
        if value in ("ok", "cold_soon", "cold", "hot_soon", "hot"):
            self.room_state = value
            self.puiul.room_state = value

    def _on_ack(self, event_id: str) -> None:
        log(f"FastAPI recorded {event_id}")

    def _on_kitchen_pass(self) -> None:
        self.last_motion = time.monotonic()

    def _on_kitchen_sos(self) -> None:
        log("SOS from the kitchen pad")
        self.ble.sos("kitchen")

    # --- start -------------------------------------------------------------------

    def calibrate(self) -> None:
        """Learns the empty room and the empty floor. Nobody in front during this."""
        log("calibrating: keep the room in front of Ecou empty for a few seconds")
        self.body.face("asleep")
        self.body.show_number(0)
        for _ in range(3):
            for angle, m in self.body.sweep(0, 180, STEP, TILT_LEVEL).items():
                self.room.learn(angle, m)
            for angle, m in self.body.sweep(0, 180, STEP, TILT_FLOOR).items():
                self.floor.learn(angle, m)
        log(f"calibrated {len(self.room.values)} room and {len(self.floor.values)} floor angles")
        self.body.look(90, TILT_LEVEL)
        self.body.blank()

    # --- one pass ----------------------------------------------------------------

    def tick(self) -> None:
        now = time.monotonic()
        self._report(now)
        self._show(now)
        if self._night() and self.mode == "look":
            self._quiet(now)
            return
        if self.mode == "look":
            self._look(now)
        elif self.mode == "search":
            self._search(now)
        elif self.mode == "ask":
            self._ask(now)

    # --- what the phone hears ------------------------------------------------------

    def _report(self, now: float) -> None:
        if now - self.last_reading < READING_EVERY or self.body.temp_c is None:
            return
        self.last_reading = now
        payload = {
            "temperature": round(self.body.temp_c, 1),
            "humidity": self.body.humidity,
            "seconds_since_motion": int(now - self.last_motion),
            "seconds_since_start": int(now - self.started),
        }
        forecast = self.forecast.predict()
        if forecast is not None:
            payload["forecast_60m"] = forecast
        self.ble.reading(payload)

    def _moved(self, now: float) -> None:
        self.last_motion = now
        if now - self.last_motion_sent > 10.0:
            self.last_motion_sent = now
            self.ble.motion()

    # --- what the senior sees -------------------------------------------------------

    def _show(self, now: float) -> None:
        if self.mode != "ask" and self.body.temp_c is not None:
            self.body.show_temp(self.body.temp_c)
        if self.mode == "ask":
            return  # the prompt owns the matrix
        if not self.phone_ok:
            face = "asleep"
        elif self.code == "red":
            face = "red"
        elif self.code == "call":
            face = "call"
        elif self.room_state in ("cold", "cold_soon"):
            face = "cold"
        elif self.room_state in ("hot", "hot_soon"):
            face = "hot"
        else:
            face = self.code if self.code in faces.FACES else "green"
        self.body.face(face)

        # The body: shiver for cold, fan for heat, nod during a call (P26)
        cold_every = {"cold": 10.0, "cold_soon": 30.0}.get(self.room_state)
        hot_every = {"hot": 20.0, "hot_soon": 60.0}.get(self.room_state)
        if cold_every and now - self.last_body > cold_every:
            self.last_body = now
            self.body.shiver(2000)
        elif hot_every and now - self.last_body > hot_every:
            self.last_body = now
            self.body.fan(5000)
        elif self.code == "call" and HAS_TILT and now - self.last_body > 2.0:
            self.last_body = now
            pan = self.tracker.track.angle if self.tracker.track else 90
            self.body.look(pan, TILT_LEVEL - 8)
            time.sleep(0.3)
            self.body.look(pan, TILT_LEVEL)

    # --- Look -------------------------------------------------------------------------

    def _look(self, now: float) -> None:
        track = self.tracker.track
        if track is None:
            sweep = self.body.sweep(0, 180, STEP, TILT_LEVEL)
        else:
            centre = int(round(track.angle / STEP) * STEP)
            sweep = self.body.sweep(
                max(0, centre - WINDOW), min(180, centre + WINDOW), STEP, TILT_LEVEL
            )
        found = candidates(sweep, self.room)
        before = self.tracker.track
        track = self.tracker.update(time.monotonic(), found)

        # Learn the room where nobody is
        busy = {a for a, _ in found}
        for angle, m in sweep.items():
            if angle not in busy:
                self.room.learn(angle, m)

        if track is None:
            if now - self.last_seen > SEARCH_AFTER:
                log("nobody seen: searching the floor")
                self.mode = "search"
                self.lying = LyingWatch(hold=LYING_HOLD)
            return
        self.last_seen = now
        if before is None or track.moved_at == track.last_seen:
            self._moved(now)
        self.body.look(track.angle, TILT_LEVEL)

        # A hand close in front of the eyes: read the gesture (P25)
        if track.distance < 0.6:
            self._gesture(now)
        else:
            self.palm_since = None

    def _gesture(self, now: float) -> None:
        window = self.body.stream(1.0)
        kind = classify(window)
        if kind == "palm":
            self.palm_since = self.palm_since or now
            if now - self.palm_since >= PALM_HOLD:
                log("palm held: SOS")
                self.ble.sos("palm")
                self.body.face("red")
                self.palm_since = None
                time.sleep(1.0)
        else:
            self.palm_since = None
            if kind == "wave":
                self.body.face("green")

    # --- Search -----------------------------------------------------------------------

    def _search(self, now: float) -> None:
        # Someone back in view ends the search
        level = self.body.sweep(0, 180, STEP * 2, TILT_LEVEL)
        if self.tracker.update(time.monotonic(), candidates(level, self.room)):
            log("someone is back")
            self.mode = "look"
            self.last_seen = now
            return
        floor = self.body.sweep(0, 180, STEP, TILT_FLOOR)
        lying = self.lying.update(time.monotonic(), find_lying(floor, self.floor))
        if lying is None:
            for angle, m in floor.items():  # an empty floor keeps the baseline fresh
                self.floor.learn(angle, m)
            return
        log(f"something lying {side_of(lying.angle)}, {lying.distance:.1f} m: asking")
        self.mode = "ask"
        self.asking = {
            "angle": lying.angle,
            "distance": lying.distance,
            "since": now if self.lying.since is None else self.lying.since,
            "scan": [round(or_far(floor.get(a)), 2) for a in range(0, 181, STEP)],
            "deadline": now + ASK_TIMEOUT,
            "frames": list(faces.scroll_frames("BINE?")),
            "frame": 0,
        }
        self.body.look(lying.angle, TILT_FLOOR)
        self.body.start_stream(50)

    # --- Ask --------------------------------------------------------------------------

    def _ask(self, now: float) -> None:
        a = self.asking
        assert a is not None
        left = a["deadline"] - now
        self.body.show_number(max(0, int(left) + 1))
        self.body.draw(a["frames"][a["frame"] % len(a["frames"])])
        a["frame"] += 1
        window = self.body.take_stream()
        kind = classify(window[-40:]) if len(window) >= 20 else "none"
        if kind == "wave":
            log("waved: fine, nothing sent")
            self._forget_object(a)
            self._end_ask("green")
            return
        if kind == "palm" or left <= 0:
            payload = {
                "seconds_still": int(now - a["since"]),
                "object_angle_deg": round(a["angle"]),
                "object_distance_m": round(a["distance"], 2),
                "scan": a["scan"],
            }
            log(f"no answer: fall sent ({side_of(a['angle'])}, {a['distance']:.1f} m)")
            self.ble.fall(payload)
            self._end_ask("yellow")
            return
        time.sleep(0.08)

    def _forget_object(self, a: dict) -> None:
        """A wave over a coat: that spot becomes floor, so it is not asked about again."""
        floor = self.body.sweep(0, 180, STEP, TILT_FLOOR)
        for angle, m in floor.items():
            if abs(angle - a["angle"]) <= 20:
                self.floor.values[angle] = or_far(m)

    def _end_ask(self, face: str) -> None:
        self.body.stop()
        self.body.blank()
        self.body.face(face)
        self.asking = None
        self.mode = "look"
        self.last_seen = time.monotonic()
        self.lying = LyingWatch(hold=LYING_HOLD)
        self.body.look(90, TILT_LEVEL)

    # --- Quiet ------------------------------------------------------------------------

    def _night(self) -> bool:
        hour = datetime.now(BUCHAREST).hour
        return hour >= 22 or hour < 7

    def _quiet(self, now: float) -> None:
        if now - self.last_quiet_sweep < QUIET_SWEEP_EVERY:
            time.sleep(1.0)
            return
        self.last_quiet_sweep = now
        floor = self.body.sweep(0, 180, STEP, TILT_FLOOR)
        if find_lying(floor, self.floor) is not None:
            # One sighting at night is not enough: Search confirms it over the hold time
            log("night sweep found something on the floor: searching")
            self.mode = "search"
            self.lying = LyingWatch(hold=LYING_HOLD)
        self.body.look(90, TILT_LEVEL)
