"""Alarm phrases (03 §4, G11, G12).

Checked against every transcribed sentence before it reaches the model, so this severity
source keeps working when the model is slow, wrong or down. The patterns are the indicative
ones from the 03 appendix; the final list is built from the spike S2 transcripts (06 §5).
"""

import re
from dataclasses import dataclass
from enum import IntEnum

# Both comma-below and cedilla forms, since transcriptions use both (03 §4).
_DIACRITICS = str.maketrans("ăâîșşțţ", "aaisstt")
# Hyphens stay: they carry meaning in „n-am”, „mi-e”, „nu-mi”.
_PUNCTUATION = re.compile(r"[^\w\s-]")
_SPACES = re.compile(r"\s+")


def normalize(sentence: str) -> str:
    """Lowercase, strip diacritics and punctuation except hyphens, collapse spaces."""
    text = sentence.lower().translate(_DIACRITICS)
    text = _PUNCTUATION.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


class Tier(IntEnum):
    # Tier 1: red and hand-over at once. Tier 2: the server asks a fixed confirmation first.
    one = 1
    two = 2


@dataclass(frozen=True)
class AlarmMatch:
    tier: Tier
    condition: str
    # The normalized words that matched, for the tier 2 question „Ați spus că [...]” and review.
    matched: str


# Not preceded by a letter or a hyphen, so „n-am căzut azi” does not read as „am căzut”.
_START = r"(?<![\w-])"

_PATTERNS: list[tuple[Tier, str, list[str]]] = [
    (
        Tier.one,
        "breathing",
        [r"nu (mai )?pot (sa )?respir", r"ma sufoc", r"n(-| )?am aer", r"ma inec"],
    ),
    (
        Tier.one,
        "chest_heart",
        [
            r"(dure\w*|doare|dor|apasa|strange|arde|junghi).{0,15}piept",
            r"piept\w*.{0,10}(doare|dor|apasa|strange)",
            r"(mana|bratul) stang",
        ],
    ),
    (
        Tier.one,
        "stroke",
        [
            r"nu-?mi simt (mana|bratul|piciorul|fata)",
            r"amort\w*.{0,15}(parte|mana|fata|piciorul)",
            r"nu pot misca",
            r"stramb\w*.{0,10}gura",
            r"vad dublu",
            r"nu (mai )?vad",
        ],
    ),
    (
        Tier.one,
        "ambulance",
        [
            r"salvare\w*",
            r"ambulant\w*",
            r"112",
            r"unu unu doi",
            r"trimite\w* pe cineva",
        ],
    ),
    (Tier.one, "bleeding", [r"sanger\w*", r"curge sange"]),
    (
        Tier.one,
        "fall",
        [
            _START + r"am cazut",
            r"nu ma pot (ridica|scula)",
            r"(stau|sunt) (pe jos|pe podea)",
            r"mi-?am rupt",
        ],
    ),
    (
        Tier.one,
        "self_harm",
        [
            r"vreau sa mor",
            r"nu (mai )?vreau sa (mai )?traiesc",
            r"sa se termine",
            r"ma omor",
        ],
    ),
    (
        Tier.two,
        "fainting",
        [r"lesin\w*", r"negru in fata ochilor", r"am picat", r"pierdut cunostint"],
    ),
    (
        Tier.two,
        "heat",
        [r"ard tot", r"nu (mai )?transpir", r"febra mare", r"nu (mai )?pot de cald"],
    ),
    (
        Tier.two,
        "cold",
        [
            r"nu-?mi simt degetele",
            r"tremur tot",
            r"n(-| )?am caldura",
            r"oprit caldura",
            r"inghet",
        ],
    ),
    (
        Tier.two,
        "dizziness_vomiting",
        [r"se invarte", r"ma invart", r"vom\w*", r"varsat"],
    ),
    (
        Tier.two,
        "help",
        [
            r"ajutor",
            r"(mi-?e|imi e) (foarte|tare|asa de) rau",
            r"rau de tot",
            r"\bmor\b",
        ],
    ),
]

# Tier 1 first, so a sentence with both is never downgraded to a confirmation.
_COMPILED = sorted(
    (
        (tier, condition, re.compile("|".join(f"(?:{p})" for p in patterns)))
        for tier, condition, patterns in _PATTERNS
    ),
    key=lambda entry: entry[0],
)


def check(sentence: str) -> AlarmMatch | None:
    """Return the most severe alarm phrase in a transcribed sentence, or None."""
    text = normalize(sentence)
    for tier, condition, pattern in _COMPILED:
        if found := pattern.search(text):
            return AlarmMatch(tier=tier, condition=condition, matched=found.group(0))
    return None


# Said by the server, not the model, on a tier 2 match (03 §4).
CONFIRMATION = (
    "Ați spus că {said}. Aveți nevoie de ajutor acum? "
    "Spuneți «da» sau apăsați 1. Dacă nu, spuneți «nu» sau apăsați 2."
)

# Said before a self-harm hand-over, and nothing else (03 §4).
SELF_HARM_HANDOVER = "Vă fac legătura acum cu cineva cu care puteți vorbi."


def confirmation_question(sentence: str) -> str:
    """The fixed tier 2 question, naming what the senior said in their own words."""
    said = sentence.strip().rstrip(".!?…").strip()
    said = said[:1].lower() + said[1:]
    return CONFIRMATION.format(said=said)


# Replies that sound like „nu” but are not a clear no.
_UNSURE = re.compile(r"\bnu (stiu|sunt sigur\w*|prea)\b")


def needs_help(reply: str | None) -> bool:
    """Interpret the reply to the tier 2 question. True means red and hand-over (03 §4).

    Key 1 or „da” is yes. Key 2 or a clear „nu” is no. Silence (None), a hang-up,
    or anything unclear counts as yes: an unanswered confirmation is red.
    """
    if reply is None:
        return True
    text = normalize(reply)
    if text == "1":
        return True
    if text == "2":
        return False
    words = set(text.split())
    said_yes = "da" in words
    said_no = "nu" in words and not _UNSURE.search(text)
    return not (said_no and not said_yes)
