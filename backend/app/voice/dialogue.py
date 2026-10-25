from xml.sax.saxutils import escape, quoteattr

from fastapi import Response

from app.core.settings import get_settings

LANGUAGE = "ro-RO"
SORRY = "Ne pare rău, apelul nu poate continua. La revedere."

# The consent the call reads, and the one the mock card shows; the version is stored
# with every consent so a text change is traceable (05 §1, design §4.4).
CONSENT_VERSION = "v1"
CONSENT_TEXT = (
    "Vă vom suna în zilele cu vreme extremă sau când ceasul semnalează ceva neobișnuit. "
    "Ce spuneți în apel văd medicul de familie, familia și DAS. Puteți renunța oricând. "
    "Dacă sunteți de acord, apăsați 1 sau spuneți «da». Dacă nu, apăsați 2 sau spuneți "
    "«nu». Ca să ascultați din nou, apăsați 0."
)
CARD_CONSENT_VERSION = "v1-app"
CARD_CONSENT_TEXT = (
    "Vă vom suna în zilele cu vreme extremă sau când ceasul semnalează ceva neobișnuit. "
    "Ce spuneți în apel văd medicul de familie, familia și DAS. Puteți renunța oricând. "
    "Sunteți de acord?"
)


def greeting(form_of_address: str) -> str:
    """The test call's opening (04 §4.2's greeting, minus the warning and the question)."""
    return (
        f"Bună ziua, {form_of_address}. Sunt asistentul automat al DAS Timișoara. "
        "Acesta este un apel de probă. Nu vă cer niciodată bani sau date. "
        "Spuneți ceva și vă repet ce am auzit. Apăsați zero ca să închideți."
    )


def twiml(body: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'
    return Response(xml, media_type="text/xml")


def say(text: str) -> str:
    """Romanian in the voice the relay speaks with (04 §4.3)."""
    s = get_settings()
    voice = f"{s.twilio_tts_provider}.{s.twilio_voice}"
    return f"<Say language={quoteattr(LANGUAGE)} voice={quoteattr(voice)}>{escape(text)}</Say>"


def say_and_hang_up(text: str) -> Response:
    return twiml(f"{say(text)}<Hangup/>")


def gather(action: str, text: str) -> Response:
    """One question of the welcome call, by key or by voice (04 §4.2, G7). An empty
    answer still calls `action`, so silence is counted there."""
    attrs = {
        "input": "dtmf speech",
        "numDigits": "1",
        "language": LANGUAGE,
        "speechTimeout": "auto",
        "timeout": "6",
        "hints": "da, nu, sunt de acord",
        "actionOnEmptyResult": "true",
        "action": action,
        "method": "POST",
    }
    tag = "".join(f" {name}={quoteattr(value)}" for name, value in attrs.items())
    return twiml(f"<Gather{tag}>{say(text)}</Gather>")


def sorry() -> Response:
    """A polite Romanian goodbye, never Twilio's own English error (06 §1)."""
    return say_and_hang_up(SORRY)
