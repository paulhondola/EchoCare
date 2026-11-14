"""Spike S14: can the UNO Q's Linux side be the home node's BLE GATT server?

08-ecou.md §6. Runs on the UNO Q's Debian, outside App Lab, and pretends to be Ecou:
the EchoCare service with the P20 characteristics and Ecou's additions (04 §3,
08-ecou.md §3.1), values as small JSON texts. The phone side is nRF Connect, so the
spike needs no change to the Android app.

    python3 -m venv ~/s14 && ~/s14/bin/pip install bless
    ~/s14/bin/python s14_ble_node.py [--name Ecou-TEST] [--interval 5]

Keys, then Enter:  s  SOS press    f  fall    m  motion    q  quit

The UUIDs are this spike's own. If Ecou is adopted they go into 04 §3 as they are.
"""

import argparse
import asyncio
import json
import logging
import random
import sys
import time
import uuid

from bless import (  # type: ignore[import-untyped]
    BlessGATTCharacteristic,
    BlessServer,
    GATTAttributePermissions,
    GATTCharacteristicProperties,
)

BASE = "ec0f{:04x}-7765-4f56-abaf-af4938f246ad"
SERVICE = BASE.format(0x0000)
ROOM_READING = BASE.format(0x0001)
MOTION = BASE.format(0x0002)
SOS_PRESS = BASE.format(0x0003)
ACKNOWLEDGE = BASE.format(0x0004)
LIGHT = BASE.format(0x0005)
FALL = BASE.format(0x0006)
ROOM_STATE = BASE.format(0x0007)

NAMES = {
    ROOM_READING: "Room reading",
    MOTION: "Motion",
    SOS_PRESS: "SOS press",
    ACKNOWLEDGE: "Acknowledge",
    LIGHT: "Light",
    FALL: "Fall",
    ROOM_STATE: "Room state",
}

NOTIFY = GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify
WRITE = GATTCharacteristicProperties.write
READABLE = GATTAttributePermissions.readable
WRITABLE = GATTAttributePermissions.writable

log = logging.getLogger("s14")
started = time.monotonic()
last_motion = time.monotonic()
# Events not yet acknowledged by the phone: id → (characteristic, when it happened)
pending: dict[str, tuple[str, float]] = {}
written: list[tuple[float, str, str]] = []  # what the phone wrote, for the summary
notified = 0


def age(since: float) -> int:
    return int(time.monotonic() - since)


def on_read(characteristic: BlessGATTCharacteristic, **kwargs) -> bytearray:
    return characteristic.value or bytearray()


def on_write(characteristic: BlessGATTCharacteristic, value, **kwargs) -> None:
    characteristic.value = value
    uuid_ = str(characteristic.uuid).lower()
    text = bytes(value).decode("utf-8", errors="replace")
    written.append((time.monotonic(), NAMES.get(uuid_, uuid_), text))
    log.info("phone wrote %s: %s", NAMES.get(uuid_, uuid_), text)
    if uuid_ == ACKNOWLEDGE:
        event_id = text.strip().strip('"')
        try:
            event_id = json.loads(text).get("id", event_id)
        except (ValueError, AttributeError):
            pass
        if pending.pop(event_id, None):
            log.info("acknowledged %s: the node would beep twice now", event_id)
        else:
            log.warning("acknowledge for an unknown id %s", event_id)


def send(server: BlessServer, char: str, payload: dict) -> None:
    global notified
    data = json.dumps(payload, separators=(",", ":")).encode()
    server.get_characteristic(char).value = bytearray(data)
    server.update_value(SERVICE, char)
    notified += 1
    log.info("notify %s (%d bytes): %s", NAMES[char], len(data), data.decode())
    if len(data) > 20:
        log.debug("over 20 bytes: needs the phone to raise the MTU (it asks for 185)")


def room_reading() -> dict:
    t = 21.0 + random.uniform(-0.3, 0.3)
    return {
        "temperature": round(t, 1),
        "humidity": round(45 + random.uniform(-2, 2)),
        "seconds_since_motion": age(last_motion),
        "seconds_since_start": age(started),
        "forecast_60m": round(t - 1.2, 1),
    }


def fall_payload(event_id: str, found: float) -> dict:
    scan = [round(random.uniform(2.5, 3.5), 2) for _ in range(37)]
    for i in range(20, 24):
        scan[i] = 2.1  # the object
    return {
        "id": event_id,
        "seconds_ago": age(found),
        "seconds_still": 8 + age(found),
        "object_angle_deg": 105,
        "object_distance_m": 2.1,
        "scan": scan,
    }


async def run(name: str, interval: float) -> None:
    global last_motion
    loop = asyncio.get_running_loop()
    server = BlessServer(name=name, loop=loop)
    server.read_request_func = on_read
    server.write_request_func = on_write

    await server.add_new_service(SERVICE)
    for char in (ROOM_READING, MOTION, SOS_PRESS, FALL):
        await server.add_new_characteristic(SERVICE, char, NOTIFY, None, READABLE)
    for char in (ACKNOWLEDGE, LIGHT, ROOM_STATE):
        await server.add_new_characteristic(SERVICE, char, WRITE, None, WRITABLE)

    await server.start()
    log.info("advertising as %s, service %s", name, SERVICE)
    log.info("keys: s SOS, f fall, m motion, q quit (then Enter)")

    stop = asyncio.Event()

    def on_key() -> None:
        global last_motion
        key = sys.stdin.readline().strip().lower()
        if key == "s":
            event_id = str(uuid.uuid4())
            pending[event_id] = (SOS_PRESS, time.monotonic())
            log.info("SOS press %s: the node would beep once now", event_id)
        elif key == "f":
            event_id = str(uuid.uuid4())
            pending[event_id] = (FALL, time.monotonic())
            log.info("fall %s", event_id)
        elif key == "m":
            last_motion = time.monotonic()
            send(server, MOTION, {})
        elif key == "q":
            stop.set()

    loop.add_reader(sys.stdin, on_key)

    next_reading = 0.0
    next_resend = 0.0
    while not stop.is_set():
        now = time.monotonic()
        if now >= next_reading:
            send(server, ROOM_READING, room_reading())
            next_reading = now + interval
        # P20 resends after a reconnection; the spike cannot see connections, so it
        # resends every few seconds until the phone acknowledges.
        if pending and now >= next_resend:
            for event_id, (char, created) in list(pending.items()):
                if char == SOS_PRESS:
                    send(
                        server,
                        SOS_PRESS,
                        {"id": event_id, "seconds_ago": age(created), "via": "button"},
                    )
                else:
                    send(server, FALL, fall_payload(event_id, created))
            next_resend = now + 3.0
        await asyncio.sleep(0.2)

    loop.remove_reader(sys.stdin)
    await server.stop()

    log.info(
        "summary: %d notifications, %d writes from the phone, %d events never acknowledged",
        notified,
        len(written),
        len(pending),
    )
    for t, char, text in written:
        log.info("  +%5.1fs  %s  %s", t - started, char, text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--name", default="Ecou-TEST")
    parser.add_argument(
        "--interval", type=float, default=5.0, help="seconds between room readings (demo mode: 5)"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(run(args.name, args.interval))


if __name__ == "__main__":
    main()
