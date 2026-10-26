from xml.sax.saxutils import escape, quoteattr

from fastapi import Response

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


# The stand-in welcome call until UC-04's real steps replace it (04 §4.2).
WELCOME_STANDIN = (
    "Bună ziua, {form_of_address}. Acesta este un apel de test EchoCare. La revedere."
)


def welcome_standin(form_of_address: str) -> Response:
    """The welcome call's one sentence, then hang up."""
    text = WELCOME_STANDIN.format(form_of_address=form_of_address)
    return twiml(f"<Say language={quoteattr(LANGUAGE)}>{escape(text)}</Say><Hangup/>")


def twiml(body: str) -> Response:
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'
    return Response(xml, media_type="text/xml")


def sorry() -> Response:
    """A polite Romanian goodbye, never Twilio's own English error (06 §1)."""
    return twiml(f"<Say language={quoteattr(LANGUAGE)}>{escape(SORRY)}</Say><Hangup/>")
