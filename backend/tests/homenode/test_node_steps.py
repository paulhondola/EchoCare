"""The home node's scheduler steps: silence (UC-13) and inactivity during a warning
(UC-16), and the room on the senior's page and the incident (04 §1)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.homenode.service import report_inactivity, silence_home_nodes
from app.models import (
    Call,
    CallTrigger,
    Campaign,
    CampaignKind,
    Event,
    EventType,
    HomeNodeState,
    NodeCondition,
    WarningLevel,
)
from tests.seniors.test_seniors import signed_in

SENIOR = "+40700000101"
NOW = datetime.now(UTC)


@pytest.fixture(autouse=True)
def demo_limits(monkeypatch):
    """30 seconds of silence, 60 of inactivity (06 §3), whatever backend/.env says."""
    monkeypatch.setattr(
        "app.homenode.service.get_settings", lambda: SimpleNamespace(demo_mode=True)
    )


@pytest.fixture
async def senior(add_active_senior):
    return await add_active_senior(SENIOR)


async def add_node(db, senior, *, read_ago=timedelta(0), still_for=None, **columns):
    db.add(
        HomeNodeState(
            senior_id=senior.id,
            state=NodeCondition.ok,
            last_reading_at=NOW - read_ago,
            temperature_c=21.0,
            last_motion_at=NOW - still_for if still_for else None,
            **columns,
        )
    )
    await db.commit()


async def add_warning(db, senior, until=timedelta(hours=24)):
    db.add(
        Campaign(
            kind=CampaignKind.cold,
            level=WarningLevel.yellow,
            started_by=senior.medic_id,
            warning_until=NOW + until,
        )
    )
    await db.commit()


async def node(db) -> HomeNodeState:
    db.expire_all()
    return await db.scalar(select(HomeNodeState))


async def events(db) -> list[Event]:
    db.expire_all()
    return list(await db.scalars(select(Event)))


async def test_a_silent_node_goes_offline_and_a_reading_brings_it_back(
    client, db, senior
):
    await add_node(db, senior, read_ago=timedelta(seconds=45))
    assert await silence_home_nodes(db, NOW) == 1
    assert (await node(db)).state is NodeCondition.offline
    assert await silence_home_nodes(db, NOW) == 0  # once

    await client.post(
        "/api/me/room-readings",
        json={"measured_at": datetime.now(UTC).isoformat(), "temperature": 20.5},
        headers=signed_in(SENIOR),
    )
    assert (await node(db)).state is NodeCondition.ok


async def test_a_recent_node_stays(db, senior):
    await add_node(db, senior, read_ago=timedelta(seconds=10))
    assert await silence_home_nodes(db, NOW) == 0


async def test_no_motion_during_a_warning_calls_once(db, senior):
    await add_node(db, senior, still_for=timedelta(minutes=2))
    await add_warning(db, senior)
    assert await report_inactivity(db, NOW) == 1
    [event] = await events(db)
    assert (event.type, event.source) == (EventType.inactivity, "home_node")
    [call] = list(await db.scalars(select(Call)))
    assert call.trigger is CallTrigger.home_node
    assert await report_inactivity(db, NOW) == 0  # one per warning


async def test_no_motion_outside_a_warning_records_nothing(db, senior):
    await add_node(db, senior, still_for=timedelta(minutes=2))
    await add_warning(db, senior, until=-timedelta(hours=1))
    assert await report_inactivity(db, NOW) == 0
    assert await events(db) == []


async def test_recent_motion_or_an_offline_node_records_nothing(db, senior):
    await add_node(db, senior, still_for=timedelta(seconds=20))
    await add_warning(db, senior)
    assert await report_inactivity(db, NOW) == 0
    stored = await node(db)
    stored.state, stored.last_motion_at = (
        NodeCondition.offline,
        NOW - timedelta(hours=1),
    )
    await db.commit()
    assert await report_inactivity(db, NOW) == 0


async def test_new_motion_rearms_the_inactivity_event(client, db, senior):
    await add_node(db, senior, still_for=timedelta(minutes=2))
    await add_warning(db, senior)
    await report_inactivity(db, NOW)
    await client.post(
        "/api/me/room-readings",
        json={
            "measured_at": datetime.now(UTC).isoformat(),
            "temperature": 20.5,
            "last_motion_at": datetime.now(UTC).isoformat(),
        },
        headers=signed_in(SENIOR),
    )
    assert (await node(db)).inactivity_event_sent is False


async def test_the_room_shows_on_the_seniors_pages(client, db, senior):
    await add_node(db, senior, humidity_pct=40.0)
    one = (
        await client.get(f"/api/seniors/{senior.id}", headers=signed_in(SENIOR))
    ).json()
    assert one["room"]["temperature"] == 21.0
    assert (one["room"]["state"], one["room"]["room_state"]) == ("ok", "ok")
    [row] = (await client.get("/api/seniors", headers=signed_in(SENIOR))).json()
    assert (row["home_node_state"], row["room_temperature"]) == ("ok", 21.0)


async def test_no_node_no_room(client, senior):
    one = (
        await client.get(f"/api/seniors/{senior.id}", headers=signed_in(SENIOR))
    ).json()
    assert one["room"] is None
