"""The welcome call's script over the phone: what it says and how it reads the answers
(UC-04, G7). A fixed script of keys and short words, so the deciding answer is a key
press or an exact match, never a guess.
"""

from typing import Any

from app.status.alarms import normalize
from app.voice.models import TurnKind, WelcomeOutcome

IDENTITY = (
    "Bună ziua. Sunt asistentul automat al DAS Timișoara. Vorbesc cu {f}? "
    "Dacă da, apăsați 1 sau spuneți «da». Dacă {f} nu poate veni acum la telefon, "
    "apăsați 2. Dacă ați primit acest apel din greșeală, apăsați 3."
)
NOT_HEARD = "Nu v-am auzit."

# How each ending says goodbye (design §2).
GIVEN = (
    "Vă mulțumim. Vă rugăm să salvați acest număr. "
    "Nu vă vom cere niciodată bani sau date. La revedere."
)
REFUSED = (
    "Am înțeles. Vă rugăm să salvați acest număr. "
    "Nu vă vom cere niciodată bani sau date. La revedere."
)
NOT_AVAILABLE = "Vă mulțumim. Vom suna din nou mai târziu. La revedere."
WRONG_NUMBER = "Ne cerem scuze pentru deranj. La revedere."
SILENT = "Nu v-am auzit. La revedere."
UNCLEAR = "Nu v-am înțeles. La revedere."

# Whole answers only, once normalized: „da, cred” is not a yes (G7).
IDENTITY_YES = frozenset({"da"})
CONSENT_YES = frozenset({"da", "sunt de acord", "da sunt de acord"})
CONSENT_NO = frozenset({"nu", "nu sunt de acord"})


def identity(form_of_address: str) -> str:
    return IDENTITY.format(f=form_of_address)


def identity_answer(digits: str, speech: str) -> WelcomeOutcome | None:
    """Who answered: the senior, someone who will fetch them later, or a stranger;
    None when nothing clear was heard."""
    if digits == "1" or normalize(speech) in IDENTITY_YES:
        return WelcomeOutcome.confirmed
    return {"2": WelcomeOutcome.not_available, "3": WelcomeOutcome.wrong_number}.get(
        digits
    )


def consent_answer(digits: str, speech: str) -> bool | None:
    """True for a consent, False for a refusal, None for anything else."""
    words = normalize(speech)
    if digits == "1" or (not digits and words in CONSENT_YES):
        return True
    if digits == "2" or (not digits and words in CONSENT_NO):
        return False
    return None


def heard(params: dict[str, str]) -> tuple[TurnKind, str, float | None] | None:
    """A `<Gather>` answer as a transcript turn: the key, or the words with Twilio's
    confidence; None for silence."""
    if digits := params.get("Digits"):
        return TurnKind.keys, digits, None
    if speech := params.get("SpeechResult", "").strip():
        return TurnKind.speech, speech, confidence(params)
    return None


def confidence(params: dict[str, str]) -> float | None:
    """Twilio's `Confidence` in the words; None when missing or not a number, so a bad
    value never fails the callback (06 §1). A reported 0.0 stays 0.0."""
    try:
        return float(params["Confidence"])
    except KeyError, ValueError:
        return None


def evidence(params: dict[str, str]) -> dict[str, Any]:
    """What the consent was decided on, kept with it (05 §1): the key, or the words and
    Twilio's confidence in them."""
    if digits := params.get("Digits"):
        return {"digits": digits}
    return {
        "speech": params.get("SpeechResult", ""),
        "confidence": confidence(params) or 0.0,
    }
