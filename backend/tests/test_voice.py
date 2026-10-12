"""Twilio's callbacks replayed against FastAPI, one with a bad signature (#15, 06 §5)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import voice
from app.main import app
from app.models import Call
from app.twilio import signature

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "twilio_callbacks.json").read_text()
)
TOKEN = "test-auth-token"  # conftest.py
SID = FIXTURES["answer"]["CallSid"]


@pytest.fixture
async def call(db, add_senior) -> Call:
    senior = await add_senior("+40700000101")
    row = Call(
        senior_id=senior.id,
        trigger="manual",
        starting_severity="green",
        due_at=datetime.now(UTC),
    )
    db.add(row)
    await db.commit()
    return row


async def callback(client, path, call_id, params, *, sign=True):
    """POSTs a form as Twilio would, signed for the public address (conftest.py)."""
    url = f"https://sentinela.test/api/voice/{path}?call={call_id}"
    header = signature(TOKEN if sign else "wrong-token", url, params.items())
    return await client.post(
        f"/api/voice/{path}?call={call_id}",
        content=urlencode(params),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": header,
        },
    )


async def stored(db, call) -> Call:
    return await db.get(Call, call.id, populate_existing=True)


async def test_answer_connects_to_conversation_relay(client, call):
    r = await callback(client, "answer", call.id, FIXTURES["answer"])
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/xml")
    assert "<Connect><ConversationRelay" in r.text
    assert f'url="wss://sentinela.test/api/voice/relay?call={call.id}"' in r.text
    assert 'language="ro-RO"' in r.text
    assert "Bună ziua, doamna Maria." in r.text


async def test_a_bad_signature_gets_403(client, db, call):
    for path, params in [
        ("answer", FIXTURES["answer"]),
        ("status", {**FIXTURES["status_common"], **FIXTURES["status"][1]}),
        ("amd", FIXTURES["amd_machine"]),
    ]:
        r = await callback(client, path, call.id, params, sign=False)
        assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_allowed"}})
    assert (await stored(db, call)).state == "queued"


async def test_a_signature_for_another_call_gets_403(client, call):
    # The call id is part of the signed address.
    url = f"https://sentinela.test/api/voice/answer?call={call.id}"
    header = signature(TOKEN, url.replace(str(call.id)[-4:], "0000"), [])
    r = await client.post(
        f"/api/voice/answer?call={call.id}", headers={"X-Twilio-Signature": header}
    )
    assert r.status_code == 403


async def test_an_answered_call_ends_completed(client, db, call):
    for event in FIXTURES["status"]:
        params = {**FIXTURES["status_common"], **event}
        r = await callback(client, "status", call.id, params)
        assert r.status_code == 204
    row = await stored(db, call)
    assert (row.state, row.twilio_call_id) == ("completed", SID)
    assert row.started_at is not None and row.ended_at >= row.started_at


@pytest.mark.parametrize("twilio_status", ["no-answer", "busy", "canceled"])
async def test_an_unanswered_call(client, db, call, twilio_status):
    for status in ("ringing", twilio_status):
        params = {**FIXTURES["status_common"], "CallStatus": status}
        await callback(client, "status", call.id, params)
    row = await stored(db, call)
    assert (row.state, row.started_at) == ("unanswered", None)
    assert row.ended_at is not None


async def test_late_and_repeated_callbacks_change_nothing(client, db, call):
    for status in ("completed", "ringing", "in-progress", "completed"):
        params = {**FIXTURES["status_common"], "CallStatus": status}
        await callback(client, "status", call.id, params)
    # completed without in-progress still means answered
    row = await stored(db, call)
    assert row.state == "completed"
    assert row.started_at is not None


async def test_a_machine_is_hung_up_and_unanswered(client, db, call, monkeypatch):
    hung_up = []

    async def fake_hang_up(sid):
        hung_up.append(sid)

    monkeypatch.setattr(voice, "hang_up", fake_hang_up)
    common = FIXTURES["status_common"]
    await callback(client, "status", call.id, {**common, "CallStatus": "in-progress"})
    r = await callback(client, "amd", call.id, FIXTURES["amd_machine"])
    assert r.status_code == 204
    assert hung_up == [SID]
    await callback(client, "status", call.id, {**common, "CallStatus": "completed"})
    assert (await stored(db, call)).state == "unanswered"


async def test_a_person_is_left_alone(client, db, call, monkeypatch):
    monkeypatch.setattr(voice, "hang_up", pytest.fail)
    common = FIXTURES["status_common"]
    await callback(client, "status", call.id, {**common, "CallStatus": "in-progress"})
    r = await callback(client, "amd", call.id, FIXTURES["amd_human"])
    assert r.status_code == 204
    assert (await stored(db, call)).state == "in_progress"


async def test_a_callback_for_an_unknown_call(client, db, call):
    params = {**FIXTURES["status_common"], "CallStatus": "ringing"}
    r = await callback(client, "status", "0190a1b2-0000-7000-8000-000000000000", params)
    assert r.status_code == 204
    r = await callback(
        client, "answer", "0190a1b2-0000-7000-8000-000000000000", FIXTURES["answer"]
    )
    assert "<Hangup/>" in r.text
    assert (await db.scalar(select(Call.state).where(Call.id == call.id))) == "queued"


def test_an_unsigned_relay_connect_is_refused():
    # Refused before the database is touched, so this needs none.
    relay = "/api/voice/relay?call=0190a1b2-0000-7000-8000-000000000000"
    unsigned = {"X-Twilio-Signature": "not-a-signature"}
    with (
        TestClient(app) as http,
        pytest.raises(WebSocketDisconnect) as closed,
        http.websocket_connect(relay, headers=unsigned),
    ):
        pass
    assert closed.value.code == 1008
