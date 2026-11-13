"""POST /me/events: the senior's „Sunați-mă” request (UC-10, 04 §3)."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import (
    Call,
    CallTrigger,
    EnrollmentState,
    Event,
    EventType,
    Role,
)
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.service import cooldown
from tests.seniors.test_seniors import NOT_ALLOWED, refusal, signed_in

SENIOR = "+40700000101"
MEDIC = "+40700000102"


@pytest.fixture
async def senior(add_active_senior):
    return await add_active_senior(SENIOR)


def request(client, event_id=None, measured_at=None, token=SENIOR, **fields):
    return client.post(
        "/api/me/events",
        json={
            "id": str(event_id or uuid.uuid4()),
            "type": "manual_request",
            "measured_at": (measured_at or datetime.now(UTC)).isoformat(),
            **fields,
        },
        headers=signed_in(token),
    )


async def calls(db) -> list[Call]:
    db.expire_all()
    return list(await db.scalars(select(Call).order_by(Call.created_at)))


async def events(db) -> list[Event]:
    db.expire_all()
    return list(await db.scalars(select(Event).order_by(Event.received_at)))


async def add_ended_call(db, senior, ended_ago: timedelta) -> Call:
    now = datetime.now(UTC)
    call = Call(
        senior_id=senior.id,
        trigger=CallTrigger.watch,
        starting_severity=Severity.yellow,
        state=CallState.completed,
        due_at=now - ended_ago,
        ended_at=now - ended_ago,
    )
    db.add(call)
    await db.commit()
    return call


async def test_a_request_queues_a_yellow_manual_call(client, db, senior):
    senior_id = senior.id
    r = await request(client)
    assert r.status_code == 200
    [call] = await calls(db)
    assert (call.trigger, call.starting_severity, call.state) == (
        CallTrigger.manual,
        Severity.yellow,
        CallState.queued,
    )
    assert call.due_at <= datetime.now(UTC)
    call_id = call.id
    assert r.json() == {"queued": True, "call_id": str(call_id)}
    [event] = await events(db)
    assert (event.senior_id, event.type, event.call_id) == (
        senior_id,
        EventType.manual_request,
        call_id,
    )


@pytest.mark.parametrize(
    ("source", "trigger"),
    [("watch", CallTrigger.watch), ("phone", CallTrigger.manual)],
)
async def test_a_watch_event_queues_a_watch_call(client, db, senior, source, trigger):
    """The call says why it rings: the watch's own trigger for its events (04 §3)."""
    await request(client, type="high_pulse_at_rest", source=source)
    [call] = await calls(db)
    assert call.trigger is trigger


async def test_a_second_tap_attaches_to_the_same_call(client, db, senior):
    first = (await request(client)).json()
    second = (await request(client)).json()
    assert second == {"queued": False, "call_id": first["call_id"]}
    assert len(await calls(db)) == 1
    assert {e.call_id for e in await events(db)} == {uuid.UUID(first["call_id"])}


async def test_a_resent_event_is_acknowledged_and_ignored(client, db, senior):
    event_id = uuid.uuid4()
    first = (await request(client, event_id)).json()
    again = await request(client, event_id)
    assert again.status_code == 200
    assert again.json() == {"queued": False, "call_id": first["call_id"]}
    assert len(await events(db)) == 1
    assert len(await calls(db)) == 1


async def test_a_call_that_just_ended_takes_the_request(client, db, senior):
    ended = await add_ended_call(db, senior, ended_ago=timedelta(seconds=5))
    r = await request(client)
    assert r.json() == {"queued": False, "call_id": str(ended.id)}
    assert len(await calls(db)) == 1


async def test_after_the_cooldown_a_request_queues_a_new_call(
    client, db, senior, monkeypatch
):
    monkeypatch.setattr(
        "app.voice.service.get_settings", lambda: SimpleNamespace(demo_mode=False)
    )
    ended = await add_ended_call(db, senior, ended_ago=timedelta(minutes=11))
    r = await request(client)
    assert r.json()["queued"] is True
    assert r.json()["call_id"] != str(ended.id)
    assert len(await calls(db)) == 2


async def test_inside_the_cooldown_in_production_it_attaches(
    client, db, senior, monkeypatch
):
    monkeypatch.setattr(
        "app.voice.service.get_settings", lambda: SimpleNamespace(demo_mode=False)
    )
    await add_ended_call(db, senior, ended_ago=timedelta(minutes=9))
    assert (await request(client)).json()["queued"] is False


async def test_a_stale_request_is_recorded_and_starts_no_call(client, db, senior):
    r = await request(client, measured_at=datetime.now(UTC) - timedelta(minutes=31))
    assert r.json() == {"queued": False, "call_id": None}
    assert len(await events(db)) == 1
    assert await calls(db) == []


async def test_a_senior_who_is_not_active_starts_no_call(client, db, senior):
    senior.enrollment_state = EnrollmentState.withdrawn
    await db.commit()
    r = await request(client)
    assert r.json() == {"queued": False, "call_id": None}
    assert len(await events(db)) == 1
    assert await calls(db) == []


async def test_only_a_senior_sends_events(client, add_user, senior):
    await add_user(MEDIC, Role.medic)
    assert refusal(await request(client, token=MEDIC)) == NOT_ALLOWED


async def test_signed_out_is_401(client, senior):
    r = await client.post("/api/me/events", json={})
    assert r.status_code == 401


async def test_an_unknown_type_is_422(client, senior):
    r = await request(client, type="not_an_event_type")
    assert r.status_code == 422


async def test_a_naive_time_is_422(client, senior):
    r = await client.post(
        "/api/me/events",
        json={
            "id": str(uuid.uuid4()),
            "type": "manual_request",
            "measured_at": "2026-10-29T10:00:00",
        },
        headers=signed_in(SENIOR),
    )
    assert r.status_code == 422


def test_the_cooldown_is_30_seconds_in_demo_mode(monkeypatch):
    for demo, wait in ((True, timedelta(seconds=30)), (False, timedelta(minutes=10))):
        monkeypatch.setattr(
            "app.voice.service.get_settings",
            lambda demo=demo: SimpleNamespace(demo_mode=demo),
        )
        assert cooldown() == wait
