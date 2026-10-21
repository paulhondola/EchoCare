"""Twilio's callbacks replayed against FastAPI, one with a bad signature (#15, 06 §5)."""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.agent import session as agent_session
from app.agent.relay import GOODBYE
from app.core.db import get_session
from app.main import app
from app.models import Call, CallTurn
from app.voice import router as voice_router
from app.voice import service as voice_service
from app.voice.dialogue import SORRY
from app.voice.twilio import signature

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
    url = f"https://echocare.test/api/voice/{path}?call={call_id}"
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
    assert f'url="wss://echocare.test/api/voice/relay?call={call.id}"' in r.text
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
    url = f"https://echocare.test/api/voice/answer?call={call.id}"
    header = signature(TOKEN, url.replace(str(call.id), str(uuid.uuid4())), [])
    r = await client.post(
        f"/api/voice/answer?call={call.id}", headers={"X-Twilio-Signature": header}
    )
    assert r.status_code == 403


async def test_a_hang_up_ends_dropped(client, db, call):
    # Twilio's completed, with no close of ours before it: they hung up (03 §9).
    for event in FIXTURES["status"]:
        params = {**FIXTURES["status_common"], **event}
        r = await callback(client, "status", call.id, params)
        assert r.status_code == 204
    row = await stored(db, call)
    assert (row.state, row.twilio_call_id) == ("dropped", SID)
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
    assert row.state == "dropped"
    assert row.started_at is not None


async def test_a_machine_is_hung_up_and_unanswered(client, db, call, monkeypatch):
    hung_up = []

    async def fake_hang_up(sid):
        hung_up.append(sid)

    monkeypatch.setattr(voice_service, "hang_up", fake_hang_up)
    common = FIXTURES["status_common"]
    await callback(client, "status", call.id, {**common, "CallStatus": "in-progress"})
    r = await callback(client, "amd", call.id, FIXTURES["amd_machine"])
    assert r.status_code == 204
    assert hung_up == [SID]
    await callback(client, "status", call.id, {**common, "CallStatus": "completed"})
    assert (await stored(db, call)).state == "unanswered"


async def test_a_person_is_left_alone(client, db, call, monkeypatch):
    monkeypatch.setattr(voice_service, "hang_up", pytest.fail)
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


async def test_unknown_status_changes_nothing(client, db, call):
    params = {**FIXTURES["status_common"], "CallStatus": "on-hold"}
    assert (await callback(client, "status", call.id, params)).status_code == 204
    assert (await stored(db, call)).state == "queued"


async def test_a_database_failure_at_pickup_says_sorry(client, call):
    class Broken:
        async def scalar(self, *_):
            raise OperationalError("SELECT", {}, OSError("connection refused"))

    app.dependency_overrides[get_session] = lambda: Broken()
    r = await callback(client, "answer", call.id, FIXTURES["answer"])
    del app.dependency_overrides[get_session]
    # Romanian, never Twilio's English application error (06 §1)
    assert r.status_code == 200
    assert SORRY in r.text and "<Hangup/>" in r.text


class Socket:
    """The relay's side of a WebSocket, signed as Twilio signs the connect (04 §4.1)."""

    def __init__(self, call_id, messages):
        self.url = SimpleNamespace(path="/api/voice/relay", query=f"call={call_id}")
        url = f"wss://echocare.test/api/voice/relay?call={call_id}"
        self.headers = {"x-twilio-signature": signature(TOKEN, url, [])}
        self.incoming = [m if isinstance(m, str) else json.dumps(m) for m in messages]
        self.sent, self.accepted, self.closed = [], False, None

    async def accept(self):
        self.accepted = True

    async def close(self, code):
        self.closed = code

    async def receive_text(self):
        if not self.incoming:
            raise WebSocketDisconnect(1000)
        return self.incoming.pop(0)

    async def send_json(self, data):
        self.sent.append(data)


SETUP = {"type": "setup", "callSid": SID}


async def answered(client, call):
    common = FIXTURES["status_common"]
    await callback(client, "status", call.id, {**common, "CallStatus": "in-progress"})


async def test_our_close_ends_completed(client, db, call):
    await answered(client, call)
    ws = Socket(call.id, [SETUP, {"type": "dtmf", "digit": "0"}])
    await voice_router.relay(ws, call.id)  # through the signature check
    assert ws.sent[-1] == {"type": "end"}
    assert (await stored(db, call)).state == "completed"
    # Twilio's completed after our close changes nothing
    params = {**FIXTURES["status_common"], **FIXTURES["status"][-1]}
    await callback(client, "status", call.id, params)
    assert (await stored(db, call)).state == "completed"
    turns = await db.scalars(
        select(CallTurn.content)
        .where(CallTurn.call_id == call.id)
        .order_by(CallTurn.position)
    )
    assert turns.all()[1:] == ["0", GOODBYE]


async def test_the_relay_skips_what_is_not_a_json_object(client, db, call):
    await answered(client, call)
    ws = Socket(call.id, [SETUP, "not json", "[1, 2]", {"type": "dtmf", "digit": "0"}])
    await agent_session.serve(ws, call.id)
    assert (ws.closed, ws.sent[-1]) == (None, {"type": "end"})


@pytest.mark.parametrize(
    "first",
    [
        {"type": "setup", "callSid": "CA" + "2" * 32},  # another call's
        {"type": "prompt", "voicePrompt": "Mă simt bine", "last": True},  # no setup
    ],
)
async def test_the_relay_needs_the_calls_own_setup_first(client, db, call, first):
    await answered(client, call)
    ws = Socket(call.id, [first, {"type": "dtmf", "digit": "0"}])
    await agent_session.serve(ws, call.id)
    assert (ws.closed, ws.sent) == (1008, [])
    assert (await stored(db, call)).state == "in_progress"


async def test_an_ended_call_takes_no_relay(client, db, call):
    # The signed address never changes, so only a live call takes a connect (Q13).
    for status in ("in-progress", "completed"):
        params = {**FIXTURES["status_common"], "CallStatus": status}
        await callback(client, "status", call.id, params)
    ws = Socket(call.id, [SETUP, {"type": "prompt", "voicePrompt": "x", "last": True}])
    await agent_session.serve(ws, call.id)
    assert (ws.accepted, ws.closed) == (False, 1008)


async def test_a_skipped_state_still_counts_answered(client, db, call):
    # A lost in-progress callback: Twilio's completed still means someone picked up and
    # hung up, so the call ends dropped, answered (03 §9). move_call may skip ahead.
    for status in ("ringing", "completed"):
        params = {**FIXTURES["status_common"], "CallStatus": status}
        await callback(client, "status", call.id, params)
    stored_call = await stored(db, call)
    assert stored_call.state == "dropped"
    assert stored_call.started_at is not None


async def test_a_dropped_relay_keeps_its_turns(client, db, call):
    # Each turn is committed as it comes, so a lost line keeps what was said (06 §1).
    await answered(client, call)
    ws = Socket(
        call.id, [SETUP, {"type": "prompt", "voicePrompt": "Bine", "last": True}]
    )
    await agent_session.serve(ws, call.id)  # the script runs out: WebSocketDisconnect
    turns = await db.scalars(
        select(CallTurn.content).where(CallTurn.call_id == call.id)
    )
    assert "Bine" in turns.all()
