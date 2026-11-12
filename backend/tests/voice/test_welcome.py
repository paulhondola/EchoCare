"""The welcome call over the phone: identity, then consent, by key or by voice (#48,
UC-04, G7). Twilio's `<Gather>` answers are replayed against FastAPI, signed."""

from datetime import UTC, datetime
from xml.etree import ElementTree

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core.db import get_session
from app.main import app
from app.models import (
    Call,
    CallTrigger,
    CallTurn,
    Consent,
    ConsentMethod,
    EnrollmentState,
    Senior,
    SeniorStatus,
    WelcomeOutcome,
)
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.dialogue import CONSENT_TEXT, SORRY
from app.voice.models import Speaker, TurnKind
from app.voice.welcome import (
    GIVEN,
    NOT_AVAILABLE,
    NOT_HEARD,
    REFUSED,
    SILENT,
    UNCLEAR,
    WRONG_NUMBER,
    heard,
    identity,
)
from tests.voice.test_voice import FIXTURES, callback, stored


@pytest.mark.parametrize(
    ("value", "expected"), [("0.0", 0.0), ("0.91", 0.91), ("x", None), (None, None)]
)
def test_heard_keeps_a_zero_confidence_and_survives_a_bad_one(value, expected):
    params = {"SpeechResult": " Da. "}
    if value is not None:
        params["Confidence"] = value
    assert heard(params) == (TurnKind.speech, "Da.", expected)


BASE = "https://echocare.test/api/voice"


@pytest.fixture
async def welcome_call(db, add_senior) -> Call:
    """A welcome call ringing an accepted senior, as the dialer leaves it."""
    senior = await add_senior("+40700000102", enrollment_state=EnrollmentState.accepted)
    row = Call(
        senior_id=senior.id,
        trigger=CallTrigger.welcome,
        starting_severity=Severity.green,
        state=CallState.ringing,
        due_at=datetime.now(UTC),
    )
    db.add(row)
    await db.commit()
    return row


def twiml(r) -> ElementTree.Element:
    assert r.status_code == 200
    return ElementTree.fromstring(r.text)


def spoken(root: ElementTree.Element) -> str:
    return " ".join(say.text for say in root.iter("Say"))


async def picked_up(client, call):
    return twiml(await callback(client, "welcome", call.id, FIXTURES["welcome"]))


def gathered(params: dict) -> dict:
    """A recorded `<Gather>` body carrying this answer (S1): with a key Twilio sends the
    speech fields empty, with speech it sends no `Digits`."""
    if "SpeechResult" in params:
        return {**FIXTURES["welcome_gather_speech"], **params}
    return {**FIXTURES["welcome_gather_keys"], "Digits": "", **params}


async def answer(client, call, step, params, ask=1):
    body = gathered(params)
    r = await callback(client, f"welcome/{step}", call.id, body, query=f"&ask={ask}")
    return twiml(r)


async def senior_of(db, call) -> Senior:
    return await db.get(Senior, call.senior_id, populate_existing=True)


async def retries(db, call) -> list[Call]:
    rows = await db.scalars(select(Call).where(Call.previous_call_id == call.id))
    return list(rows)


async def test_pickup_asks_who_answers(client, db, welcome_call):
    root = await picked_up(client, welcome_call)
    (gather,) = root.iter("Gather")
    assert gather.get("action") == (
        f"{BASE}/welcome/identity?call={welcome_call.id}&ask=1"
    )
    assert (gather.get("input"), gather.get("numDigits"), gather.get("language")) == (
        "dtmf speech",
        "1",
        "ro-RO",
    )
    assert gather.get("actionOnEmptyResult") == "true"
    say = gather.find("Say")
    assert say.text == identity("doamna Maria")
    assert say.text.count("doamna Maria") == 2
    assert say.get("voice") == "ElevenLabs.X6vOWkVPB3AcILSfttxa"
    assert (await stored(db, welcome_call)).state == CallState.in_progress


@pytest.mark.parametrize(
    "params", [{"Digits": "1"}, {"SpeechResult": "Da.", "Confidence": "0.91"}]
)
async def test_yes_at_identity_asks_for_consent(client, welcome_call, params):
    await picked_up(client, welcome_call)
    root = await answer(client, welcome_call, "identity", params)
    (gather,) = root.iter("Gather")
    assert gather.get("action") == (
        f"{BASE}/welcome/consent?call={welcome_call.id}&ask=1"
    )
    assert spoken(root) == CONSENT_TEXT


async def test_silence_at_identity_asks_again_then_says_goodbye(
    client, db, welcome_call
):
    await picked_up(client, welcome_call)
    root = await answer(client, welcome_call, "identity", {})
    (gather,) = root.iter("Gather")
    assert gather.get("action").endswith("&ask=2")
    assert spoken(root) == f"{NOT_HEARD} {identity('doamna Maria')}"

    root = await answer(client, welcome_call, "identity", {}, ask=2)
    assert spoken(root) == SILENT and root.find("Hangup") is not None
    row = await stored(db, welcome_call)
    assert (row.state, row.welcome_outcome) == (
        CallState.completed,
        WelcomeOutcome.no_answer,
    )
    assert len(await retries(db, welcome_call)) == 1


@pytest.mark.parametrize(
    ("digits", "said", "outcome", "state"),
    [
        ("2", NOT_AVAILABLE, WelcomeOutcome.not_available, EnrollmentState.accepted),
        ("3", WRONG_NUMBER, WelcomeOutcome.wrong_number, EnrollmentState.wrong_number),
    ],
)
async def test_identity_keys(client, db, welcome_call, digits, said, outcome, state):
    await picked_up(client, welcome_call)
    root = await answer(client, welcome_call, "identity", {"Digits": digits})
    assert spoken(root) == said and root.find("Hangup") is not None
    assert (await stored(db, welcome_call)).welcome_outcome == outcome
    assert (await senior_of(db, welcome_call)).enrollment_state == state


@pytest.mark.parametrize(
    ("params", "evidence"),
    [
        ({"Digits": "1"}, {"digits": "1"}),
        (
            {"SpeechResult": "DA!", "Confidence": "0.8"},
            {"speech": "DA!", "confidence": 0.8},
        ),
        (
            {"SpeechResult": "Sunt de acord.", "Confidence": "0.7"},
            {"speech": "Sunt de acord.", "confidence": 0.7},
        ),
        (
            {"SpeechResult": "da, sunt de acord", "Confidence": "0.9"},
            {"speech": "da, sunt de acord", "confidence": 0.9},
        ),
    ],
)
async def test_consent_given(client, db, welcome_call, params, evidence):
    await picked_up(client, welcome_call)
    root = await answer(client, welcome_call, "consent", params)
    assert spoken(root) == GIVEN and root.find("Hangup") is not None
    assert (await senior_of(db, welcome_call)).enrollment_state == (
        EnrollmentState.active
    )
    assert (await db.get(SeniorStatus, welcome_call.senior_id)).code == Severity.green
    consent = await db.scalar(select(Consent))
    assert (consent.method, consent.text_version, consent.evidence) == (
        ConsentMethod.call,
        "v1",
        evidence,
    )
    row = await stored(db, welcome_call)
    assert (row.state, row.welcome_outcome) == (
        CallState.completed,
        WelcomeOutcome.confirmed,
    )


async def test_the_whole_welcome_call_is_stored_in_order(client, db, welcome_call):
    await picked_up(client, welcome_call)
    await answer(client, welcome_call, "identity", {"Digits": ""})
    await answer(client, welcome_call, "identity", {"Digits": "1"}, ask=2)
    await answer(
        client, welcome_call, "consent", {"SpeechResult": "Da.", "Confidence": "0.91"}
    )
    rows = await db.scalars(
        select(CallTurn)
        .where(CallTurn.call_id == welcome_call.id)
        .order_by(CallTurn.position)
    )
    question = identity("doamna Maria")
    assert [(t.position, t.speaker, t.kind, t.content, t.confidence) for t in rows] == [
        (0, Speaker.agent, TurnKind.speech, question, None),
        (1, Speaker.agent, TurnKind.speech, f"{NOT_HEARD} {question}", None),
        (2, Speaker.senior, TurnKind.keys, "1", None),
        (3, Speaker.agent, TurnKind.speech, CONSENT_TEXT, None),
        (4, Speaker.senior, TurnKind.speech, "Da.", pytest.approx(0.91)),
        (5, Speaker.agent, TurnKind.speech, GIVEN, None),
    ]


@pytest.mark.parametrize("params", [{"Digits": "2"}, {"SpeechResult": "Nu."}])
async def test_consent_refused(client, db, welcome_call, params):
    await picked_up(client, welcome_call)
    root = await answer(client, welcome_call, "consent", params)
    assert spoken(root) == REFUSED
    assert (await senior_of(db, welcome_call)).enrollment_state == (
        EnrollmentState.refused
    )


async def test_key_0_reads_the_consent_again_without_counting(client, welcome_call):
    await picked_up(client, welcome_call)
    root = await answer(client, welcome_call, "consent", {"Digits": "0"})
    (gather,) = root.iter("Gather")
    assert gather.get("action").endswith("&ask=1")
    assert spoken(root) == CONSENT_TEXT


async def test_a_maybe_is_not_a_consent(client, db, welcome_call):
    await picked_up(client, welcome_call)
    root = await answer(client, welcome_call, "consent", {"SpeechResult": "Da, cred"})
    (gather,) = root.iter("Gather")
    assert gather.get("action").endswith("&ask=2")
    assert spoken(root) == CONSENT_TEXT

    root = await answer(
        client, welcome_call, "consent", {"SpeechResult": "Da, cred"}, ask=2
    )
    assert spoken(root) == UNCLEAR
    assert await db.scalar(select(func.count()).select_from(Consent)) == 0
    assert len(await retries(db, welcome_call)) == 1
    assert (await senior_of(db, welcome_call)).enrollment_state == (
        EnrollmentState.accepted
    )


async def test_a_repeated_gather_action_records_nothing_twice(client, db, welcome_call):
    await picked_up(client, welcome_call)
    await answer(client, welcome_call, "consent", {"Digits": "1"})
    root = await answer(client, welcome_call, "consent", {"Digits": "1"})
    assert root.find("Hangup") is not None
    assert await db.scalar(select(func.count()).select_from(Consent)) == 1


async def test_a_gather_for_an_ended_call_hangs_up(client, db, welcome_call):
    welcome_call.state = CallState.completed
    await db.commit()
    root = await answer(client, welcome_call, "identity", {"Digits": "3"})
    assert spoken(root) == SORRY and root.find("Hangup") is not None
    assert (await senior_of(db, welcome_call)).enrollment_state == (
        EnrollmentState.accepted
    )
    assert (await stored(db, welcome_call)).welcome_outcome is None


async def test_a_welcome_for_an_unknown_call_says_sorry(client, db, welcome_call):
    await db.delete(welcome_call)
    await db.commit()
    root = await picked_up(client, welcome_call)
    assert spoken(root) == SORRY and root.find("Hangup") is not None


async def test_a_database_failure_at_the_welcome_says_sorry(client, welcome_call):
    class Broken:
        async def scalar(self, *_):
            raise OperationalError("SELECT", {}, OSError("connection refused"))

    app.dependency_overrides[get_session] = lambda: Broken()
    try:
        root = await picked_up(client, welcome_call)
    finally:
        del app.dependency_overrides[get_session]
    # Romanian, never Twilio's English application error (06 §1)
    assert spoken(root) == SORRY and root.find("Hangup") is not None


@pytest.mark.parametrize("path", ["welcome", "welcome/identity", "welcome/consent"])
async def test_welcome_callbacks_refuse_a_bad_signature(client, welcome_call, path):
    r = await callback(client, path, welcome_call.id, {}, sign=False, query="&ask=1")
    assert r.status_code == 403
