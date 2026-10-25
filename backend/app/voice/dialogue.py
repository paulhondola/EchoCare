from xml.sax.saxutils import escape, quoteattr

from fastapi import Response

from app.core.settings import get_settings

LANGUAGE = "ro-RO"
SORRY = "Ne pare rău, apelul nu poate continua. La revedere."
# When the hand-over reaches nobody (UC-07).
CALL_BACK = "Un coleg vă va suna înapoi în cel mai scurt timp."

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


# Why a wellbeing call rings, by trigger (04 §4.2). Plain strings, since `voice` can't
# import `campaigns`' enums.
WHY = {
    "watch": "Vă sun pentru că ceasul a semnalat ceva neobișnuit.",
    "manual": "Vă sun pentru că ați cerut să vorbim.",
}
LEVELS = {"yellow": "galben", "red": "roșu"}
KINDS = {"cold": "ger", "heat": "caniculă"}


def wellbeing_greeting(
    form_of_address: str,
    trigger: str,
    kind: str | None = None,
    level: str | None = None,
) -> str:
    """A wellbeing call's opening, built from its trigger and, for a campaign, the
    warning (04 §4.2); a test call keeps the S1 greeting."""
    if trigger == "test":
        return greeting(form_of_address)
    if trigger == "campaign":
        why = f"Vă sun pentru că azi e cod {LEVELS[level]} de {KINDS[kind]}."
        question = "Cum vă simțiți azi?"
    else:
        why, question = WHY[trigger], "Cum vă simțiți?"
    return (
        f"Bună ziua, {form_of_address}. Sunt asistentul DAS Timișoara. {why} "
        f"Nu vă cer niciodată bani sau date. {question}"
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


def hangup() -> Response:
    return twiml("<Hangup/>")


def dial_on_duty(
    number: str, *, ring: int, result_url: str, answered_url: str
) -> Response:
    """Rings the on-duty DAS phone from the project's number (04 §4.4 step 4).
    `answered_url` is fetched when it picks up, before the two are connected."""
    caller = quoteattr(get_settings().twilio_from_number)
    dial = f"callerId={caller} timeout={quoteattr(str(ring))}"
    dial += f' action={quoteattr(result_url)} method="POST"'
    who = (
        f'<Number url={quoteattr(answered_url)} method="POST">{escape(number)}</Number>'
    )
    return twiml(f"<Dial {dial}>{who}</Dial>")
