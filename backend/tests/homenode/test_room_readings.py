"""POST /me/room-readings: the home node's room rule (UC-16, P21) and room state (P26)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.homenode.service import room_state
from app.models import (
    Call,
    CallTrigger,
    EnrollmentState,
    Event,
    EventType,
    HomeNodeState,
    NodeCondition,
    Role,
    RoomState,
)
from app.status.engine import Severity
from tests.seniors.test_seniors import NOT_ALLOWED, refusal, signed_in

SENIOR = "+40700000101"
MEDIC = "+40700000102"


@pytest.fixture
async def senior(add_active_senior):
    return await add_active_senior(SENIOR)


@pytest.fixture(autouse=True)
def demo_hold_time(monkeypatch):
    """A 30-second hold time, whatever backend/.env says (06 §3)."""
    monkeypatch.setattr(
        "app.homenode.service.get_settings", lambda: SimpleNamespace(demo_mode=True)
    )


def reading(client, temperature, ago=timedelta(0), token=SENIOR, **fields):
    return client.post(
        "/api/me/room-readings",
        json={
            "measured_at": (datetime.now(UTC) - ago).isoformat(),
            "temperature": temperature,
            **fields,
        },
        headers=signed_in(token),
    )


async def node(db) -> HomeNodeState | None:
    db.expire_all()
    return await db.scalar(select(HomeNodeState))


async def events(db) -> list[Event]:
    db.expire_all()
    return list(await db.scalars(select(Event).order_by(Event.received_at)))


async def calls(db) -> list[Call]:
    db.expire_all()
    return list(await db.scalars(select(Call)))


@pytest.mark.parametrize(
    ("celsius", "forecast", "expected"),
    [
        (21.0, None, RoomState.ok),
        (21.0, 20.0, RoomState.ok),
        (17.0, 15.0, RoomState.cold_soon),
        (28.0, 31.0, RoomState.hot_soon),
        (15.9, None, RoomState.cold),
        (15.9, 25.0, RoomState.cold),  # the room now wins over the forecast
        (30.1, None, RoomState.hot),
        (16.0, None, RoomState.ok),  # "below 16" and "above 30" (06 §3)
        (30.0, None, RoomState.ok),
    ],
)
def test_room_state(celsius, forecast, expected):
    assert room_state(celsius, forecast) is expected


async def test_a_first_reading_makes_the_node(client, db, senior):
    r = await reading(client, 21.5, humidity=40, forecast_60m=20.8)
    assert r.status_code == 200
    assert r.json() == {"room_state": "ok", "queued": False, "call_id": None}
    stored = await node(db)
    assert (
        stored.state,
        stored.temperature_c,
        stored.humidity_pct,
        stored.forecast_60m_c,
        stored.out_of_range_since,
    ) == (NodeCondition.ok, 21.5, 40.0, 20.8, None)


async def test_a_cold_forecast_warns_and_calls_nobody(client, db, senior):
    r = await reading(client, 17.0, forecast_60m=14.5)
    assert r.json()["room_state"] == "cold_soon"
    assert await calls(db) == []


async def test_a_cold_room_calls_after_the_hold_time_once(client, db, senior):
    senior_id = senior.id
    first = await reading(client, 14.0, ago=timedelta(seconds=40))
    assert first.json() == {"room_state": "cold", "queued": False, "call_id": None}
    assert await events(db) == []

    second = (await reading(client, 13.8)).json()
    assert second["room_state"] == "cold"
    assert second["queued"] is True
    [event] = await events(db)
    assert (
        event.senior_id,
        event.type,
        event.source,
        event.snapshot["temperature"],
    ) == (
        senior_id,
        EventType.room_cold,
        "home_node",
        13.8,
    )
    [call] = await calls(db)
    assert (str(call.id), call.trigger, call.starting_severity) == (
        second["call_id"],
        CallTrigger.manual,
        Severity.yellow,
    )

    # Still cold: the same stretch, no second event
    third = (await reading(client, 13.5)).json()
    assert third["queued"] is False
    assert len(await events(db)) == 1


async def test_a_room_back_in_range_before_the_hold_time_records_nothing(
    client, db, senior
):
    await reading(client, 14.0, ago=timedelta(seconds=20))
    await reading(client, 18.0, ago=timedelta(seconds=10))
    r = await reading(client, 14.0)
    assert r.json()["queued"] is False
    assert await events(db) == []
    assert (await node(db)).out_of_range_since is not None  # a new stretch started


async def test_a_new_stretch_records_a_new_event(client, db, senior):
    await reading(client, 14.0, ago=timedelta(seconds=120))
    await reading(client, 14.0, ago=timedelta(seconds=80))
    await reading(client, 20.0, ago=timedelta(seconds=70))
    await reading(client, 14.0, ago=timedelta(seconds=60))
    await reading(client, 14.0, ago=timedelta(seconds=20))
    assert [e.type for e in await events(db)] == [EventType.room_cold] * 2


async def test_a_hot_room(client, db, senior):
    await reading(client, 33.0, ago=timedelta(seconds=40))
    r = await reading(client, 33.5)
    assert r.json()["room_state"] == "hot"
    [event] = await events(db)
    assert event.type is EventType.room_heat


async def test_an_older_reading_changes_nothing(client, db, senior):
    await reading(client, 21.0)
    r = await reading(client, 10.0, ago=timedelta(minutes=5))
    assert r.json()["room_state"] == "ok"
    assert (await node(db)).temperature_c == 21.0


async def test_an_implausible_reading_is_used_for_nothing(client, db, senior):
    r = await reading(client, 85.0)
    assert r.status_code == 200
    assert r.json() == {"room_state": "ok", "queued": False, "call_id": None}
    assert await node(db) is None


async def test_a_senior_who_is_not_active_gets_no_call(client, db, senior):
    senior.enrollment_state = EnrollmentState.withdrawn
    await db.commit()
    await reading(client, 14.0, ago=timedelta(seconds=40))
    r = await reading(client, 14.0)
    assert r.json()["queued"] is False
    assert len(await events(db)) == 1
    assert await calls(db) == []


async def test_a_naive_time_is_refused(client, senior):
    r = await client.post(
        "/api/me/room-readings",
        json={"measured_at": "2026-11-14T12:00:00", "temperature": 20},
        headers=signed_in(SENIOR),
    )
    assert r.status_code == 422


async def test_only_a_senior_sends_readings(client, add_user, senior):
    await add_user(MEDIC, Role.medic)
    assert refusal(await reading(client, 20.0, token=MEDIC)) == NOT_ALLOWED
