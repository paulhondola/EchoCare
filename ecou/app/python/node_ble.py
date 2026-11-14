"""Ecou as the home node's GATT server, for the senior's phone app (04 §3, 08-ecou.md
§3.1). Values are small JSON texts. Runs its own asyncio loop on a thread, so the
robot's main loop only calls plain methods.

Whether the board's Linux side can do this from inside App Lab is spike S14. If `bless`
is missing or BlueZ refuses, `start()` returns False and Ecou runs without a phone:
the face shows „asleep” and nothing reaches FastAPI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable

log = logging.getLogger("ecou.ble")

BASE = "ec0f{:04x}-7765-4f56-abaf-af4938f246ad"
SERVICE = BASE.format(0x0000)
ROOM_READING = BASE.format(0x0001)
MOTION = BASE.format(0x0002)
SOS_PRESS = BASE.format(0x0003)
ACKNOWLEDGE = BASE.format(0x0004)
LIGHT = BASE.format(0x0005)
FALL = BASE.format(0x0006)
ROOM_STATE = BASE.format(0x0007)

NOTIFY_CHARS = (ROOM_READING, MOTION, SOS_PRESS, FALL)
WRITE_CHARS = (ACKNOWLEDGE, LIGHT, ROOM_STATE)
RESEND_S = 5.0  # an unacknowledged press or fall goes again this often


class NodeServer:
    def __init__(
        self,
        name: str,
        on_light: Callable[[str], None],
        on_room_state: Callable[[str], None],
        on_acknowledged: Callable[[str], None],
    ) -> None:
        self.name = name
        self.on_light = on_light
        self.on_room_state = on_room_state
        self.on_acknowledged = on_acknowledged
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server = None
        # id → (characteristic, payload builder): kept until the phone acknowledges
        self._pending: dict[str, tuple[str, Callable[[], dict]]] = {}
        self._lock = threading.Lock()
        self.last_write = 0.0  # when the phone last wrote anything: a sign of a link

    # --- life -------------------------------------------------------------------

    def start(self, timeout: float = 15.0) -> bool:
        ready = threading.Event()
        ok = {"value": False}

        def run() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._serve())
                ok["value"] = True
            except Exception:
                log.exception("BLE server failed to start (spike S14)")
            ready.set()
            if ok["value"]:
                self._loop.create_task(self._resend_forever())
                self._loop.run_forever()

        threading.Thread(target=run, name="ble", daemon=True).start()
        ready.wait(timeout)
        return ok["value"]

    async def _serve(self) -> None:
        from bless import (  # imported here so a missing package only disables BLE
            BlessServer,
            GATTAttributePermissions,
            GATTCharacteristicProperties,
        )

        server = BlessServer(name=self.name, loop=self._loop)
        server.read_request_func = lambda characteristic, **_: characteristic.value or bytearray()
        server.write_request_func = self._on_write
        await server.add_new_service(SERVICE)
        notify = GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify
        for char in NOTIFY_CHARS:
            await server.add_new_characteristic(
                SERVICE, char, notify, None, GATTAttributePermissions.readable
            )
        for char in WRITE_CHARS:
            await server.add_new_characteristic(
                SERVICE,
                char,
                GATTCharacteristicProperties.write,
                None,
                GATTAttributePermissions.writable,
            )
        await server.start()
        self._server = server
        log.info("advertising as %s", self.name)

    # --- from the phone ---------------------------------------------------------

    def _on_write(self, characteristic, value, **_) -> None:
        self.last_write = time.monotonic()
        char = str(characteristic.uuid).lower()
        text = bytes(value).decode("utf-8", errors="replace").strip()
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = text
        if isinstance(parsed, dict):
            parsed = parsed.get("id") or parsed.get("value") or ""
        parsed = str(parsed).strip('"')
        if char == LIGHT:
            self.on_light(parsed)
        elif char == ROOM_STATE:
            self.on_room_state(parsed)
        elif char == ACKNOWLEDGE:
            with self._lock:
                known = self._pending.pop(parsed, None)
            if known is not None:
                self.on_acknowledged(parsed)
            else:
                log.info("acknowledge for an unknown id %s", parsed)

    # --- to the phone -----------------------------------------------------------

    def _notify(self, char: str, payload: dict) -> None:
        if self._server is None or self._loop is None:
            return
        data = bytearray(json.dumps(payload, separators=(",", ":")).encode())

        def send() -> None:
            self._server.get_characteristic(char).value = data
            self._server.update_value(SERVICE, char)

        self._loop.call_soon_threadsafe(send)

    def reading(self, payload: dict) -> None:
        self._notify(ROOM_READING, payload)

    def motion(self) -> None:
        self._notify(MOTION, {})

    def sos(self, via: str) -> str:
        """An SOS press (04 §3), kept until the phone acknowledges it."""
        event_id = str(uuid.uuid4())
        made = time.monotonic()
        self._keep(
            event_id,
            SOS_PRESS,
            lambda: {"id": event_id, "seconds_ago": int(time.monotonic() - made), "via": via},
        )
        return event_id

    def fall(self, payload: dict) -> str:
        """A fall from the floor search (P24), kept until the phone acknowledges it."""
        event_id = str(uuid.uuid4())
        made = time.monotonic()
        self._keep(
            event_id,
            FALL,
            lambda: {
                "id": event_id,
                "seconds_ago": int(time.monotonic() - made),
                **payload,
            },
        )
        return event_id

    def _keep(self, event_id: str, char: str, build: Callable[[], dict]) -> None:
        with self._lock:
            self._pending[event_id] = (char, build)
        self._notify(char, build())

    async def _resend_forever(self) -> None:
        # P20 resends after a reconnection; bless does not report connections, so
        # anything unacknowledged simply goes again every few seconds.
        while True:
            await asyncio.sleep(RESEND_S)
            with self._lock:
                pending = list(self._pending.values())
            for char, build in pending:
                self._notify(char, build())

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._pending)
