"""Ecou's body: the sketch's commands and measurements over the Bridge, as plain Python
calls (08-ecou.md §2). Everything that touches the hardware goes through here.

The sketch's notifications arrive on the Bridge's thread; the handlers below only store
them, under a lock, and never call the Bridge back.
"""

from __future__ import annotations

import threading
import time
from collections import deque

import faces
import numpy as np
from arduino.app_utils import Bridge, Frame
from sensing import echo_to_m

DISPLAY_BLANK = -32768


class Body:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.temp_c: float | None = None
        self.humidity: float | None = None
        self.temp_ok = 0
        self.temp_failed = 0
        self._temp_listeners: list = []
        self._stream: deque[tuple[float, int]] = deque(maxlen=400)
        self._sweep: dict[int, int] = {}
        self._sweep_seq = 0
        self._sweep_done = threading.Event()
        self._frame_shown: str | None = None
        Bridge.provide("temp", self._on_temp)
        Bridge.provide("dist", self._on_dist)
        Bridge.provide("sweep_pt", self._on_sweep_pt)
        Bridge.provide("sweep_end", self._on_sweep_end)

    # --- notifications (Bridge thread) -------------------------------------------

    def _on_temp(self, ms: int, tenths_c: int, tenths_rh: int, ok: int) -> None:
        with self._lock:
            if ok:
                self.temp_c, self.humidity = tenths_c / 10.0, tenths_rh / 10.0
                self.temp_ok += 1
            else:
                self.temp_failed += 1
            listeners = list(self._temp_listeners)
        if ok:
            for listen in listeners:
                listen(time.monotonic(), tenths_c / 10.0)

    def _on_dist(self, ms: int, pan: int, tilt: int, echo_us: int) -> None:
        with self._lock:
            self._stream.append((time.monotonic(), echo_us))

    def _on_sweep_pt(self, seq: int, pan: int, tilt: int, echo_us: int) -> None:
        with self._lock:
            if seq == self._sweep_seq or self._sweep_seq == 0:
                self._sweep[pan] = echo_us

    def _on_sweep_end(self, seq: int) -> None:
        with self._lock:
            self._sweep_seq = seq
        self._sweep_done.set()

    def on_temperature(self, listen) -> None:
        """`listen(t, celsius)` for every good reading."""
        with self._lock:
            self._temp_listeners.append(listen)

    # --- eyes --------------------------------------------------------------------

    def sweep(
        self, start: int, end: int, step: int, tilt: int, timeout: float = 8.0
    ) -> dict[int, float | None]:
        """One sweep, blocking until it ends: angle → metres (None for no echo)."""
        with self._lock:
            self._sweep = {}
            self._sweep_seq = 0
        self._sweep_done.clear()
        Bridge.call("sweep", start, end, step, tilt)
        self._sweep_done.wait(timeout)
        with self._lock:
            raw, celsius = dict(self._sweep), self.temp_c
        return {angle: echo_to_m(us, celsius) for angle, us in raw.items()}

    def stream(self, seconds: float, period_ms: int = 50) -> list[float | None]:
        """Pings straight ahead for `seconds`, blocking: the distances in order."""
        with self._lock:
            self._stream.clear()
        Bridge.call("stream", period_ms)
        time.sleep(seconds)
        Bridge.call("stop")
        with self._lock:
            samples, celsius = list(self._stream), self.temp_c
        return [echo_to_m(us, celsius) for _, us in samples]

    def start_stream(self, period_ms: int = 50) -> None:
        with self._lock:
            self._stream.clear()
        Bridge.call("stream", period_ms)

    def take_stream(self) -> list[float | None]:
        """What arrived since the last take, without stopping."""
        with self._lock:
            samples, celsius = list(self._stream), self.temp_c
            self._stream.clear()
        return [echo_to_m(us, celsius) for _, us in samples]

    def stop(self) -> None:
        Bridge.call("stop")

    # --- neck and arm -----------------------------------------------------------

    def look(self, pan: float, tilt: float) -> None:
        Bridge.call("look", int(round(pan)), int(round(tilt)))

    def shiver(self, ms: int) -> None:
        Bridge.call("shiver", ms)

    def fan(self, ms: int) -> None:
        Bridge.call("fan", ms)

    def arm(self, deg: int) -> None:
        Bridge.call("arm", deg)

    # --- face and display -------------------------------------------------------

    def face(self, name: str) -> None:
        """One of faces.FACES; drawn only when it changes."""
        if name == self._frame_shown:
            return
        self.draw(faces.FACES[name])
        self._frame_shown = name

    def draw(self, frame: np.ndarray) -> None:
        Bridge.call("draw", Frame(frame).to_board_bytes())
        self._frame_shown = None

    def show_temp(self, celsius: float) -> None:
        Bridge.call("show_temp", int(round(celsius * 10)))

    def show_number(self, n: int) -> None:
        Bridge.call("show_number", n)

    def blank(self) -> None:
        Bridge.call("show_number", DISPLAY_BLANK)
