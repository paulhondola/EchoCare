import json
import re
from xml.sax.saxutils import escape, quoteattr

from fastapi import Response

from app.core.settings import get_settings
from app.voice.models import Speaker

LANGUAGE = "ro-RO"
# Words a wellbeing call's answers use, for the relay's speech-to-text (04 §4.3):
# „Mă stim?” was heard for „Mă simt”.
HINTS = (
    "da, nu, bine, rău, mă simt, amețit, luni, marți, miercuri, joi, vineri, "
    "sâmbătă, duminică, cald, frig, răcoare, acasă"
)
SORRY = "Ne pare rău, apelul nu poate continua. La revedere."
# When the hand-over reaches nobody (UC-07).
CALL_BACK = "Un coleg vă va suna înapoi în cel mai scurt timp."

# The consent the call reads, and the one the mock card shows; the version is stored
# with every consent so a text change is traceable (05 §1, design §4.4).
CONSENT_VERSION = "v2"
CONSENT_TEXT = (
    "Vă vom suna în zilele cu vreme extremă sau când ceasul semnalează ceva neobișnuit. "
    "Ce spuneți în apel văd medicul de familie, familia și DAS. "
    "Dacă medicul a adăugat fișa medicală, o folosim ca să vă punem întrebări potrivite. "
    "Puteți renunța oricând. "
    "Dacă sunteți de acord, apăsați 1 sau spuneți «da». Dacă nu, apăsați 2 sau spuneți "
    "«nu». Ca să ascultați din nou, apăsați 0."
)
CARD_CONSENT_VERSION = "v2-app"
CARD_CONSENT_TEXT = (
    "Vă vom suna în zilele cu vreme extremă sau când ceasul semnalează ceva neobișnuit. "
    "Ce spuneți în apel văd medicul de familie, familia și DAS. "
    "Dacă medicul a adăugat fișa medicală, o folosim ca să vă punem întrebări potrivite. "
    "Puteți renunța oricând. "
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


# The briefing's summary sentence is cut to this many words: the senior waits while DAS
# hears it (design 2026-11-14 §6).
BRIEFING_SUMMARY_WORDS = 20


def briefing(
    form_of_address: str,
    full_name: str,
    address: str | None,
    reason: str | None,
    narrative: str | None,
) -> str:
    """What the on-duty phone hears before a hand-over connects: who, where, her words
    (else the reason), the summary's first sentence (design 2026-11-14 §6). Missing parts
    are skipped."""
    parts = ["Predare EchoCare.", f"{form_of_address}, {full_name}"]
    parts[-1] += f", {address}." if address else "."
    words = re.search(r"«([^»]+)»", reason or "")
    if words:
        parts.append(f"A spus: «{words[1]}».")
    elif reason:
        parts.append(f"Motiv: {reason.rstrip('.')}.")
    if narrative:
        first = re.split(r"(?<=[.!?])\s", narrative.strip(), maxsplit=1)[0]
        parts.append("Pe scurt: " + " ".join(first.split()[:BRIEFING_SUMMARY_WORDS]))
    parts.append("Vă conectez.")
    return " ".join(parts)


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
    number: str, *, ring: int, result_url: str, answered_url: str, transcript_url: str
) -> Response:
    """Rings the on-duty DAS phone from the project's number (04 §4.4 step 4), with
    both sides transcribed to `transcript_url` first. `answered_url` is fetched when it
    picks up, before the two are connected."""
    caller = quoteattr(get_settings().twilio_from_number)
    dial = f"callerId={caller} timeout={quoteattr(str(ring))}"
    dial += f' action={quoteattr(result_url)} method="POST"'
    who = (
        f'<Number url={quoteattr(answered_url)} method="POST">{escape(number)}</Number>'
    )
    return twiml(f"{transcribe(transcript_url)}<Dial {dial}>{who}</Dial>")


# The hand-over's talk, as text only: Twilio transcribes it live and keeps no audio
# (04 §4.4, 06 §4). Deepgram's nova-3 lists Romanian; Google's telephony model doesn't.
# Deepgram knows it only as "ro": Twilio passes "ro-RO" through and gets 32651.
TRANSCRIPTION = "handover"
TRANSCRIPTION_ATTRS = {
    "name": TRANSCRIPTION,
    "track": "both_tracks",
    "languageCode": "ro",
    "transcriptionEngine": "deepgram",
    "speechModel": "nova-3",
}
# The transcription runs on the senior's leg: Twilio hears her on the inbound track
# and plays her the DAS employee on the outbound one.
TRACKS = {"inbound_track": Speaker.senior, "outbound_track": Speaker.das}


def transcribe(url: str) -> str:
    attrs = {**TRANSCRIPTION_ATTRS, "statusCallbackUrl": url}
    tag = "".join(f" {name}={quoteattr(value)}" for name, value in attrs.items())
    return f"<Start><Transcription{tag}/></Start>"


TRANSCRIPTION_FAILED = "Convorbirea cu DAS nu a putut fi transcrisă"

# Before a sentence of ours, which the outbound track would put down as DAS's.
STOP_TRANSCRIPTION = f'<Stop><Transcription name="{TRANSCRIPTION}"/></Stop>'


def transcribed(params: dict[str, str]) -> tuple[Speaker, str, float | None] | None:
    """A final sentence from a transcription callback, with who said it and Twilio's
    confidence; None for any other event, a partial or an empty sentence."""
    speaker = TRACKS.get(params.get("Track", ""))
    if (
        params.get("TranscriptionEvent") != "transcription-content"
        or params.get("Final") != "true"
        or speaker is None
    ):
        return None
    try:
        data = json.loads(params.get("TranscriptionData", ""))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    words = str(data.get("transcript", "")).strip()
    confidence = data.get("confidence")
    if not words:
        return None
    return (
        speaker,
        words,
        float(confidence) if isinstance(confidence, int | float) else None,
    )
