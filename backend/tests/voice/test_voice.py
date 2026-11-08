"""Twilio's callbacks replayed against FastAPI, one with a bad signature (#15, 06 §5)."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from xml.etree import ElementTree

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.agent import session as agent_session
from app.agent.model import ToolCall
from app.agent.relay import GOODBYE
from app.core.db import get_session
from app.main import app
from app.models import Call, CallTurn, Campaign, Incident, StatusReport
from app.status.engine import WEEKDAYS, today_in_bucharest
from app.voice import router as voice_router
from app.voice.dialogue import SORRY, greeting
from app.voice.router import echo_for
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


async def callback(client, path, call_id, params, *, sign=True, query=""):
    """POSTs a form as Twilio would, signed for the public address (conftest.py).
    `query` goes after `call=<id>`, as "&ask=2"."""
    url = f"https://echocare.test/api/voice/{path}?call={call_id}{query}"
    header = signature(TOKEN if sign else "wrong-token", url, params.items())
    return await client.post(
        f"/api/voice/{path}?call={call_id}{query}",
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
    connect = ElementTree.fromstring(r.text).find("Connect")
    # The session's end comes back here, with hand-over data or without (04 §4.4).
    assert (
        connect.get("action")
        == f"https://echocare.test/api/voice/handoff?call={call.id}"
    )
    relay = connect.find("ConversationRelay")
    assert relay.get("url") == f"wss://echocare.test/api/voice/relay?call={call.id}"
    assert relay.get("language") == "ro-RO"
    assert relay.get("welcomeGreeting").startswith("Bună ziua, doamna Maria.")
    # Words and keys over the greeting still reach the session.
    assert relay.get("reportInputDuringAgentSpeech") == "any"
    # Its own voice on a speakerphone is not the senior; a turn ends after 2 s.
    assert relay.get("echoPromptFiltering") == "true"
    assert relay.get("speechTimeout") == "2000"


def welcome_greeting(r) -> str:
    assert r.status_code == 200
    return (
        ElementTree.fromstring(r.text)
        .find("Connect/ConversationRelay")
        .get("welcomeGreeting")
    )


@pytest.fixture
def wellbeing_call(db, add_senior):
    """wellbeing_call(trigger, kind=None, level=None): a ringing call of that trigger,
    with its campaign for a campaign call."""

    async def make(trigger, kind=None, level=None) -> Call:
        senior = await add_senior("+40700000103", enrollment_state="active")
        campaign = None
        if trigger == "campaign":
            campaign = Campaign(
                kind=kind,
                level=level,
                started_by=senior.medic_id,
                warning_until=datetime.now(UTC) + timedelta(hours=24),
            )
            db.add(campaign)
            await db.flush()
        row = Call(
            senior_id=senior.id,
            trigger=trigger,
            campaign_id=campaign and campaign.id,
            starting_severity="green",
            state="ringing",
            due_at=datetime.now(UTC),
        )
        db.add(row)
        await db.commit()
        return row

    return make


async def test_a_welcome_call_answered_at_answer_gets_the_welcome(
    client, db, add_senior
):
    senior = await add_senior("+40700000104", enrollment_state="accepted")
    row = Call(
        senior_id=senior.id,
        trigger="welcome",
        starting_severity="green",
        due_at=datetime.now(UTC),
    )
    db.add(row)
    await db.commit()
    r = await callback(client, "answer", row.id, FIXTURES["answer"])
    gather = ElementTree.fromstring(r.text).find("Gather")
    assert gather.get("action") == (
        f"https://echocare.test/api/voice/welcome/identity?call={row.id}&ask=1"
    )


@pytest.mark.parametrize(
    ("kind", "level", "words"),
    [
        ("cold", "red", "Vă sun pentru că azi e cod roșu de ger."),
        ("heat", "yellow", "Vă sun pentru că azi e cod galben de caniculă."),
    ],
)
async def test_a_campaign_call_greets_with_its_warning(
    client, wellbeing_call, kind, level, words
):
    call = await wellbeing_call("campaign", kind, level)
    said = welcome_greeting(
        await callback(client, "answer", call.id, FIXTURES["answer"])
    )
    assert said == (
        f"Bună ziua, doamna Maria. Sunt asistentul DAS Timișoara. {words} "
        "Nu vă cer niciodată bani sau date. Cum vă simțiți azi?"
    )


@pytest.mark.parametrize(
    ("trigger", "words"),
    [
        ("watch", "Vă sun pentru că ceasul a semnalat ceva neobișnuit."),
        ("manual", "Vă sun pentru că ați cerut să vorbim."),
    ],
)
async def test_wellbeing_greetings(client, wellbeing_call, trigger, words):
    call = await wellbeing_call(trigger)
    said = welcome_greeting(
        await callback(client, "answer", call.id, FIXTURES["answer"])
    )
    assert said == (
        f"Bună ziua, doamna Maria. Sunt asistentul DAS Timișoara. {words} "
        "Nu vă cer niciodată bani sau date. Cum vă simțiți?"
    )


async def test_a_test_call_keeps_the_s1_greeting(client, wellbeing_call):
    call = await wellbeing_call("test")
    said = welcome_greeting(
        await callback(client, "answer", call.id, FIXTURES["answer"])
    )
    assert said == greeting("doamna Maria")


async def test_the_transcript_opens_with_the_same_greeting(client, db, call):
    said = welcome_greeting(
        await callback(client, "answer", call.id, FIXTURES["answer"])
    )
    await answered(client, call)
    ws = Socket(call.id, [SETUP])
    await voice_router.relay(ws, call.id)
    first = await db.scalar(
        select(CallTurn.content)
        .where(CallTurn.call_id == call.id)
        .order_by(CallTurn.position)
    )
    assert first == said


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

    monkeypatch.setattr(voice_router, "hang_up", fake_hang_up)
    common = FIXTURES["status_common"]
    await callback(client, "status", call.id, {**common, "CallStatus": "in-progress"})
    r = await callback(client, "amd", call.id, FIXTURES["amd_machine"])
    assert r.status_code == 204
    assert hung_up == [SID]
    await callback(client, "status", call.id, {**common, "CallStatus": "completed"})
    assert (await stored(db, call)).state == "unanswered"


async def test_a_person_is_left_alone(client, db, call, monkeypatch):
    monkeypatch.setattr(voice_router, "hang_up", pytest.fail)
    common = FIXTURES["status_common"]
    await callback(client, "status", call.id, {**common, "CallStatus": "in-progress"})
    # In IE1 a person comes back `unknown`, never `human` (S1).
    r = await callback(client, "amd", call.id, FIXTURES["amd_unknown"])
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

        execute = scalar

    app.dependency_overrides[get_session] = lambda: Broken()
    r = await callback(client, "answer", call.id, FIXTURES["answer"])
    del app.dependency_overrides[get_session]
    # Romanian, never Twilio's English application error (06 §1)
    assert r.status_code == 200
    assert SORRY in r.text and "<Hangup/>" in r.text


class Socket:
    """The relay's side of a WebSocket, signed as Twilio signs the connect (04 §4.1)."""

    def __init__(self, call_id, messages, drain: float = 0):
        self.drain = drain
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
            if self.drain:  # lets a turn task finish
                await asyncio.sleep(self.drain)
                self.drain = 0
            raise WebSocketDisconnect(1000)
        return self.incoming.pop(0)

    async def send_json(self, data):
        self.sent.append(data)


SETUP = {"type": "setup", "callSid": SID}


async def answered(client, call):
    common = FIXTURES["status_common"]
    await callback(client, "status", call.id, {**common, "CallStatus": "in-progress"})


async def test_our_close_ends_completed(client, db, call):
    call.trigger = "test"
    await db.commit()
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
    await agent_session.serve(ws, call.id, echo_for(call.id, "Bună ziua."))
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
    await agent_session.serve(ws, call.id, echo_for(call.id, "Bună ziua."))
    assert (ws.closed, ws.sent) == (1008, [])
    assert (await stored(db, call)).state == "in_progress"


async def test_an_ended_call_takes_no_relay(client, db, call):
    # The signed address never changes, so only a live call takes a connect (Q13).
    for status in ("in-progress", "completed"):
        params = {**FIXTURES["status_common"], "CallStatus": status}
        await callback(client, "status", call.id, params)
    ws = Socket(call.id, [SETUP, {"type": "prompt", "voicePrompt": "x", "last": True}])
    await agent_session.serve(ws, call.id, echo_for(call.id, "Bună ziua."))
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
    await agent_session.serve(
        ws, call.id, echo_for(call.id, "Bună ziua.")
    )  # the script runs out: WebSocketDisconnect
    turns = await db.scalars(
        select(CallTurn.content).where(CallTurn.call_id == call.id)
    )
    assert "Bine" in turns.all()


async def test_key_9_on_a_wellbeing_call_ends_handed_over(client, db, call):
    await answered(client, call)
    ws = Socket(call.id, [SETUP, {"type": "dtmf", "digit": "9"}])
    await voice_router.relay(ws, call.id)
    end = ws.sent[-1]
    assert end["type"] == "end"
    assert json.loads(end["handoffData"]) == {"call": str(call.id), "reason": "key_9"}
    assert (await stored(db, call)).state == "handed_over"
    assert await db.scalar(select(func.count()).select_from(Incident)) == 1
    # Twilio's completed once the hand-over is over changes nothing (03 §9)
    params = {**FIXTURES["status_common"], **FIXTURES["status"][-1]}
    await callback(client, "status", call.id, params)
    assert (await stored(db, call)).state == "handed_over"


async def test_key_9_on_a_test_call_writes_nothing(client, db, call):
    call.trigger = "test"
    await db.commit()
    await answered(client, call)
    ws = Socket(call.id, [SETUP, {"type": "dtmf", "digit": "9"}])
    await voice_router.relay(ws, call.id)
    assert ws.sent[-1] == {"type": "text", "token": "Ați apăsat tasta 9.", "last": True}
    assert (await stored(db, call)).state == "in_progress"
    assert await db.scalar(select(func.count()).select_from(Incident)) == 0
    assert await db.scalar(select(func.count()).select_from(StatusReport)) == 0


async def test_a_wellbeing_call_talks_to_the_model(client, db, call, monkeypatch):
    async def stream(messages):
        yield "Mă bucur. Ce zi e azi?"

    monkeypatch.setattr(voice_router, "model_stream", lambda: stream)
    await answered(client, call)
    ws = Socket(
        call.id,
        [SETUP, {"type": "prompt", "voicePrompt": "bine", "last": True}],
        drain=0.2,
    )
    await voice_router.relay(ws, call.id)
    assert {"type": "text", "token": "Mă bucur. Ce zi e azi?", "last": True} in ws.sent


async def test_a_test_call_still_echoes(client, db, call):
    call.trigger = "test"
    await db.commit()
    await answered(client, call)
    ws = Socket(
        call.id, [SETUP, {"type": "prompt", "voicePrompt": "bine", "last": True}]
    )
    await voice_router.relay(ws, call.id)
    assert ws.sent[0]["token"].startswith("Am auzit")


async def test_a_model_hand_over_sends_reason_agent(client, db, call, monkeypatch):
    async def stream(messages):
        yield ToolCall("c1", "request_human", {"reason": "nu aude"})

    monkeypatch.setattr(voice_router, "model_stream", lambda: stream)
    await answered(client, call)
    ws = Socket(
        call.id,
        [SETUP, {"type": "prompt", "voicePrompt": "alo?", "last": True}],
        drain=0.2,
    )
    await voice_router.relay(ws, call.id)
    assert json.loads(ws.sent[-1]["handoffData"])["reason"] == "agent"
    assert (await stored(db, call)).state == "handed_over"


async def test_serve_closes_the_handler_on_any_error(client, db, call):
    """The agent's limit and turn tasks stop with the socket (session.py)."""
    await answered(client, call)

    class Failing:
        closed = False

        async def handle(self, message):
            if message["type"] == "prompt":
                raise RuntimeError("database down")

        async def close(self):
            Failing.closed = True

    ws = Socket(call.id, [SETUP, {"type": "prompt", "voicePrompt": "x", "last": True}])
    with pytest.raises(RuntimeError):
        await agent_session.serve(ws, call.id, lambda send: Failing())
    assert Failing.closed


async def test_three_clear_answers_end_the_call_completed(
    client, db, call, monkeypatch
):
    """#49's done when: the model records three clear answers and ends the call."""
    today = WEEKDAYS[today_in_bucharest().weekday()]

    def record(field, value):
        args = {"field": field, "value": value, "clear": True, "words": value}
        return ToolCall(f"c-{field}", "record_answer", args)

    async def stream(messages):
        yield record("feeling", "ok")
        yield record("orientation", today)
        yield record("shelter", "yes")
        yield ToolCall("c-end", "end_call", {"summary": "Doamna se simte bine."})
        yield "Vă mulțumesc. La revedere."

    monkeypatch.setattr(voice_router, "model_stream", lambda: stream)
    await answered(client, call)
    ws = Socket(
        call.id,
        [SETUP, {"type": "prompt", "voicePrompt": "bine, e " + today, "last": True}],
        drain=0.2,
    )
    await voice_router.relay(ws, call.id)
    assert ws.sent[-1] == {"type": "end"}
    ended = await stored(db, call)
    assert ended.state == "completed"
    assert ended.final_severity is not None
    assert ended.summary.startswith("Doamna se simte bine.")
