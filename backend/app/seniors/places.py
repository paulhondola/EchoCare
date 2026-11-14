"""Approximate senior locations for the dashboard's map, from a fixed table of Timișoara
streets (design 2026-11-14 §7). Offline on purpose: an address never leaves the server.

ponytail: street-level only, one point per street; store coordinates if a pilot needs the door.
"""

import re
import uuid

from app.status.alarms import normalize

# The word before a street's name, dropped so "Str. Mărășești" and "Mărășești" match
_PREFIX = re.compile(
    r"^(strada|str|calea|bulevardul|bulevard|bd|b-dul|piata|aleea|splaiul|intrarea)\s+"
)

# One point on each street, by its normalized name. Every street in scripts/seed.py is here,
# plus main streets a senior may be registered on during the demo. Approximate.
STREETS: dict[str, tuple[float, float]] = {
    # scripts/seed.py
    "cetatii": (45.7600, 21.2235),
    "eroilor de la tisa": (45.7395, 21.2190),
    "take ionescu": (45.7615, 21.2380),
    "aradului": (45.7700, 21.2265),
    "buziasului": (45.7350, 21.2580),
    "girocului": (45.7330, 21.2280),
    "lipovei": (45.7720, 21.2420),
    "martirilor": (45.7280, 21.2140),
    "sagului": (45.7305, 21.2030),
    "alba iulia": (45.7545, 21.2265),
    "aries": (45.7385, 21.2335),
    "bucovinei": (45.7660, 21.2440),
    "cluj": (45.7545, 21.2390),
    "gheorghe lazar": (45.7525, 21.2150),
    "memorandumului": (45.7530, 21.2190),
    "marasesti": (45.7560, 21.2280),
    "pestalozzi": (45.7450, 21.2130),
    # Main streets
    "revolutiei din 1989": (45.7550, 21.2300),
    "16 decembrie 1989": (45.7480, 21.2100),
    "mihai viteazu": (45.7470, 21.2290),
    "republicii": (45.7570, 21.2330),
    "vasile parvan": (45.7470, 21.2350),
    "constantin diaconovici loga": (45.7555, 21.2330),
    "iosif bulbuca": (45.7380, 21.2450),
    "liviu rebreanu": (45.7400, 21.2440),
    "dambovita": (45.7425, 21.2010),
    "torontalului": (45.7700, 21.1980),
    "stefan cel mare": (45.7450, 21.2200),
    "victoriei": (45.7535, 21.2255),
    "unirii": (45.7580, 21.2290),
    "simion barnutiu": (45.7470, 21.2420),
    "circumvalatiunii": (45.7650, 21.2050),
    "gheorghe doja": (45.7600, 21.2080),
    "3 august 1919": (45.7560, 21.2010),
    "ion creanga": (45.7520, 21.2420),
    "dorobantilor": (45.7380, 21.2560),
    "bogdanestilor": (45.7510, 21.2480),
}

# Up to ~80 m north and ~55 m east, so neighbours on one street get their own pins
_SPREAD = 0.0007


def approx_location(
    senior_id: uuid.UUID, street: str | None
) -> tuple[float, float] | None:
    """A point on the senior's street, nudged by her id; None for a street not in the table."""
    if not street:
        return None
    base = STREETS.get(_PREFIX.sub("", normalize(street)))
    if base is None:
        return None
    a, b = senior_id.bytes[-2:]
    return base[0] + a / 256 * _SPREAD, base[1] + b / 256 * _SPREAD
