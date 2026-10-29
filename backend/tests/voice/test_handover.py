"""The hand-over callbacks: dial the on-duty DAS phone, take the incident on answer,
and say someone will call back otherwise (#48, 04 §4.2, §4.4, UC-07)."""

import json
import uuid
from datetime import UTC, datetime
from xml.etree import ElementTree

import pytest
from sqlalchemy import select, update

from app.core.settings import get_settings
from app.models import (
    Call,
    CallTrigger,
    Incident,
    IncidentStatus,
    Role,
    User,
)
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.dialogue import CALL_BACK
from app.voice.twilio import handover_ring_seconds
from tests.voice.test_voice import FIXTURES, callback, stored

BASE = "https://echocare.test/api/voice"
DAS = "+40700000001"


@pytest.fixture
async def handed_over(db, add_active_senior) -> Call:
    """A call key 9 handed over, with the incident it opened (Task 4)."""
    senior = await add_active_senior("+40700000105")
    call = Call(
        senior_id=senior.id,
        trigger=CallTrigger.manual,
        starting_severity=Severity.yellow,
        state=CallState.handed_over,
        due_at=datetime.now(UTC),
    )
    db.add(call)
    await db.flush()
    db.add(
        Incident(
            senior_id=senior.id,
            status=IncidentStatus.open,
            opened_by_call_id=call.id,
            reason="A cerut un operator (tasta 9)",
        )
    )
    await db.commit()
    return call


@pytest.fixture
async def on_duty_das(db, add_user) -> User:
    user = await add_user(DAS, Role.das, name="DAS de serviciu")
    await db.execute(update(User).where(User.id == user.id).values(on_duty=True))
    await db.commit()
    return user


@pytest.fixture
def allow(monkeypatch):
    monkeypatch.setattr(get_settings(), "dial_allowlist", DAS)


def handoff(call, reason="key_9") -> dict:
    data = json.dumps({"call": str(call.id), "reason": reason})
    return {**FIXTURES["handoff"], "HandoffData": data}


def dialed(status: str) -> dict:
    return {**FIXTURES["handoff_result"], "DialCallStatus": status}


def twiml(r) -> ElementTree.Element:
    assert r.status_code == 200
    return ElementTree.fromstring(r.text)


def says_call_back(root) -> bool:
    said = [say.text for say in root.iter("Say")]
    return said == [CALL_BACK] and root.find("Hangup") is not None


async def incident_of(db, call) -> Incident:
    return await db.scalar(
        select(Incident)
        .where(Incident.opened_by_call_id == call.id)
        .execution_options(populate_existing=True)
    )


async def test_nobody_on_duty_hears_the_call_back_line(client, handed_over):
    root = twiml(
        await callback(client, "handoff", handed_over.id, handoff(handed_over))
    )
    assert says_call_back(root)
    assert root.find("Dial") is None


async def test_the_on_duty_phone_is_dialed(
    client, handed_over, on_duty_das, allow, monkeypatch
):
    monkeypatch.setattr(get_settings(), "twilio_from_number", "+15005550006")
    root = twiml(
        await callback(client, "handoff", handed_over.id, handoff(handed_over))
    )
    dial = root.find("Dial")
    assert (dial.get("callerId"), dial.get("timeout")) == (
        "+15005550006",
        str(handover_ring_seconds()),
    )
    assert dial.get("action") == f"{BASE}/handoff-result?call={handed_over.id}"
    number = dial.find("Number")
    assert number.text == DAS
    assert number.get("url") == (
        f"{BASE}/handoff-answered?call={handed_over.id}&user={on_duty_das.id}"
    )


async def test_an_on_duty_number_off_the_allowlist_is_not_dialed(
    client, handed_over, on_duty_das
):
    root = twiml(
        await callback(client, "handoff", handed_over.id, handoff(handed_over))
    )
    assert says_call_back(root)
    assert root.find("Dial") is None


@pytest.mark.parametrize(
    "data", [None, "not json", json.dumps({"call": str(uuid.uuid4())})]
)
async def test_no_usable_handoff_data_hangs_up(
    client, handed_over, on_duty_das, allow, data
):
    params = {k: v for k, v in FIXTURES["handoff"].items() if k != "HandoffData"}
    if data is not None:
        params["HandoffData"] = data
    root = twiml(await callback(client, "handoff", handed_over.id, params))
    assert root.find("Hangup") is not None
    assert root.find("Dial") is None and root.find("Say") is None


async def test_answering_takes_the_incident(client, db, handed_over, on_duty_das):
    r = await callback(
        client,
        "handoff-answered",
        handed_over.id,
        FIXTURES["handoff_answered"],
        query=f"&user={on_duty_das.id}",
    )
    root = twiml(r)
    assert len(root) == 0  # nothing to say: Twilio connects the two
    incident = await incident_of(db, handed_over)
    assert (incident.status, incident.taken_by) == (
        IncidentStatus.in_progress,
        on_duty_das.id,
    )
    assert (await stored(db, handed_over)).handover_answered is True


async def test_an_incident_already_taken_stays_theirs(
    client, db, handed_over, on_duty_das, add_user
):
    other = await add_user("+40700000003", Role.das, name="Alt DAS")
    await db.execute(
        update(Incident)
        .where(Incident.opened_by_call_id == handed_over.id)
        .values(status=IncidentStatus.in_progress, taken_by=other.id)
    )
    await db.commit()
    await callback(
        client,
        "handoff-answered",
        handed_over.id,
        FIXTURES["handoff_answered"],
        query=f"&user={on_duty_das.id}",
    )
    assert (await incident_of(db, handed_over)).taken_by == other.id
    assert (await stored(db, handed_over)).handover_answered is True


async def test_no_answer_says_someone_will_call_back(client, db, handed_over):
    r = await callback(client, "handoff-result", handed_over.id, dialed("no-answer"))
    assert says_call_back(twiml(r))
    assert (await stored(db, handed_over)).handover_answered is False
    assert (await incident_of(db, handed_over)).status == IncidentStatus.open


async def test_a_late_no_answer_keeps_an_answered_hand_over(client, db, handed_over):
    handed_over.handover_answered = True
    await db.commit()
    await callback(client, "handoff-result", handed_over.id, dialed("busy"))
    assert (await stored(db, handed_over)).handover_answered is True


async def test_a_completed_dial_hangs_up(client, db, handed_over):
    r = await callback(client, "handoff-result", handed_over.id, dialed("completed"))
    root = twiml(r)
    assert root.find("Hangup") is not None and root.find("Say") is None


@pytest.mark.parametrize("path", ["handoff", "handoff-answered", "handoff-result"])
async def test_handoff_callbacks_refuse_a_bad_signature(client, handed_over, path):
    r = await callback(
        client, path, handed_over.id, {}, sign=False, query=f"&user={uuid.uuid4()}"
    )
    assert r.status_code == 403
