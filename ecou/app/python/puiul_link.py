"""Ecou's side of the link with Puiul, the R4 WiFi in the kitchen (P27, 08-ecou.md §2.6).

Puiul sends small JSON datagrams to UDP port 4210: `{"id": 17, "type": "pass"}`,
`"sos"` or `"alive"`. Ecou answers each with the room state and the code, so Puiul
learns where to send without any setup beyond the network.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from collections.abc import Callable

log = logging.getLogger("ecou.puiul")

PORT = 4210
SILENT_AFTER_S = 120.0  # no `alive` for this long: kitchen motion stops counting


class PuiulLink:
    def __init__(self, on_pass: Callable[[], None], on_sos: Callable[[], None]) -> None:
        self.on_pass = on_pass
        self.on_sos = on_sos
        self.room_state = "ok"
        self.code = "green"
        self.last_heard = 0.0
        self._seen: set[tuple[str, int]] = set()

    def start(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", PORT))
        except OSError:
            log.exception("cannot listen for Puiul on UDP %d", PORT)
            return False
        threading.Thread(target=self._listen, args=(sock,), name="puiul", daemon=True).start()
        log.info("listening for Puiul on UDP %d", PORT)
        return True

    @property
    def alive(self) -> bool:
        return time.monotonic() - self.last_heard < SILENT_AFTER_S

    def _listen(self, sock: socket.socket) -> None:
        while True:
            data, addr = sock.recvfrom(256)
            try:
                msg = json.loads(data)
                kind, msg_id = str(msg["type"]), int(msg.get("id", 0))
            except (ValueError, KeyError, TypeError):
                continue
            self.last_heard = time.monotonic()
            # Puiul repeats an SOS until answered; act on each id once
            key = (addr[0], msg_id)
            if kind in ("pass", "sos") and key not in self._seen:
                self._seen.add(key)
                if len(self._seen) > 500:
                    self._seen.clear()
                (self.on_pass if kind == "pass" else self.on_sos)()
            reply = {"ack": msg_id, "room_state": self.room_state, "code": self.code}
            try:
                sock.sendto(json.dumps(reply).encode(), addr)
            except OSError:
                pass
