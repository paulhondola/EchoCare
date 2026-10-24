"""POST /me/check-ins and the watch silence step (UC-13, #47)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import Role, WatchCondition, WatchState
from app.seniors.service import silence_watches, watch_silence
from tests.seniors.test_seniors import NOT_ALLOWED, refusal, signed_in

SENIOR = "+40700000101"
MEDIC = "+40700000102"


@pytest.fixture
async def senior(add_active_senior):
    return await add_active_senior(SENIOR)


def check_in(client, measured_at=None, token=SENIOR, **fields):
    measured_at = measured_at or datetime.now(UTC)
    return client.post(
        "/api/me/check-ins",
        json={"measured_at": measured_at.isoformat(), **fields},
        headers=signed_in(token),
    )


async def stored(db, senior) -> WatchState:
    """The test's one watch state; `senior` only says a senior exists."""
    db.expire_all()
    return await db.scalar(select(WatchState))


async def test_a_first_check_in_creates_the_watch_state(client, db, senior):
    r = await check_in(client, battery=80, worn=True, last_pulse=72)
    assert r.status_code == 204
    watch = await stored(db, senior)
    assert (watch.state, watch.battery, watch.worn, watch.last_pulse) == (
        WatchCondition.ok,
        80,
        True,
        72,
    )


async def test_not_worn(client, db, senior):
    await check_in(client, worn=False)
    assert (await stored(db, senior)).state is WatchCondition.not_worn


async def test_an_older_check_in_changes_nothing(client, db, senior):
    first = datetime.now(UTC) - timedelta(minutes=1)
    await check_in(client, first, battery=80)
    await check_in(client, first - timedelta(minutes=5), battery=10, worn=False)
    watch = await stored(db, senior)
    assert (watch.last_check_in_at, watch.battery, watch.state) == (
        first,
        80,
        WatchCondition.ok,
    )


async def test_a_future_time_is_stored_as_arrival(client, db, senior):
    before = datetime.now(UTC)
    await check_in(client, before + timedelta(hours=1))
    stamp = (await stored(db, senior)).last_check_in_at
    assert before <= stamp <= datetime.now(UTC)


async def test_a_naive_time_is_422(client, senior):
    r = await client.post(
        "/api/me/check-ins",
        json={"measured_at": "2026-10-24T10:00:00"},
        headers=signed_in(SENIOR),
    )
    assert r.status_code == 422


async def test_only_a_senior_checks_in(client, add_user, senior):
    await add_user(MEDIC, Role.medic)
    assert refusal(await check_in(client, token=MEDIC)) == NOT_ALLOWED


async def test_a_silent_watch_goes_offline_and_comes_back(
    db, client, senior, monkeypatch
):
    monkeypatch.setattr(
        "app.seniors.service.get_settings", lambda: SimpleNamespace(demo_mode=False)
    )
    now = datetime.now(UTC)
    await check_in(client, now - timedelta(minutes=50))
    assert await silence_watches(db, now) == 1
    assert (await stored(db, senior)).state is WatchCondition.offline
    await check_in(client, now)
    assert (await stored(db, senior)).state is WatchCondition.ok


async def test_a_watch_inside_the_limit_stays(db, client, senior, monkeypatch):
    monkeypatch.setattr(
        "app.seniors.service.get_settings", lambda: SimpleNamespace(demo_mode=False)
    )
    now = datetime.now(UTC)
    await check_in(client, now - timedelta(minutes=30))
    assert await silence_watches(db, now) == 0
    assert (await stored(db, senior)).state is WatchCondition.ok


def test_silence_is_90_seconds_in_demo_mode(monkeypatch):
    for demo, limit in ((True, timedelta(seconds=90)), (False, timedelta(minutes=45))):
        monkeypatch.setattr(
            "app.seniors.service.get_settings",
            lambda demo=demo: SimpleNamespace(demo_mode=demo),
        )
        assert watch_silence() == limit
