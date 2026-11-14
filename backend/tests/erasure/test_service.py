"""Erasing a senior through each table's owner (design 2026-11-14, ADR-005)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Grant, PushToken, Role, User
from app.auth.service import Caller
from app.codes.models import ReportSource, SeniorStatus, StatusReport
from app.core.db import Base, Session
from app.erasure.service import erase_senior
from app.homenode.models import HomeNodeState, NodeCondition
from app.incidents.models import (
    Event,
    EventType,
    Incident,
    IncidentOutcome,
    IncidentStatus,
)
from app.medical.models import MedicalRecord
from app.seniors.models import (
    Consent,
    ConsentDecision,
    ConsentMethod,
    Senior,
    SummaryVersion,
    WatchCondition,
    WatchReading,
    WatchState,
)
from app.status.engine import Question, Severity
from app.voice.calls import CallState
from app.voice.models import Answer, Call, CallTrigger, CallTurn, Speaker, TurnKind
from app.voice.service import append_turn, take_for_dialing

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


async def caller_for(db: AsyncSession, user: User) -> Caller:
    grants = list(await db.scalars(select(Grant).where(Grant.user_id == user.id)))
    return Caller(user, grants)


def add_call(db: AsyncSession, senior: Senior, **columns) -> Call:
    call = Call(
        senior_id=senior.id,
        trigger=columns.pop("trigger", CallTrigger.campaign),
        starting_severity=Severity.green,
        state=columns.pop("state", CallState.completed),
        due_at=NOW,
        **columns,
    )
    db.add(call)
    return call


async def count(db: AsyncSession, model, *where) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(*where))


@pytest.fixture
async def das(add_user) -> User:
    return await add_user("+40700000001", Role.das, name="Dispecer")


async def add_caregiver(db: AsyncSession, add_user, senior: Senior, phone: str) -> User:
    user = await add_user(phone, name="Ion Pop")
    db.add(
        Grant(
            user_id=user.id,
            role=Role.caregiver,
            senior_id=senior.id,
            granted_by=senior.medic_id,
        )
    )
    await db.commit()
    return user


async def test_erase_removes_every_row(
    db: AsyncSession, add_user, add_active_senior, das: User
):
    senior = await add_active_senior("+40700000101")
    caregiver = await add_caregiver(db, add_user, senior, "+40700000201")
    first = add_call(db, senior)
    await db.flush()
    second = add_call(db, senior, previous_call_id=first.id)
    await db.flush()
    db.add_all(
        [
            Consent(
                senior_id=senior.id,
                decision=ConsentDecision.given,
                method=ConsentMethod.call,
                text_version="v2",
                call_id=first.id,
            ),
            SummaryVersion(
                senior_id=senior.id, call_id=second.id, content={}, model="m"
            ),
            WatchState(
                senior_id=senior.id, state=WatchCondition.ok, last_check_in_at=NOW
            ),
            WatchReading(senior_id=senior.id, measured_at=NOW),
            WatchReading(senior_id=senior.id, measured_at=NOW - timedelta(hours=1)),
            HomeNodeState(
                senior_id=senior.id,
                state=NodeCondition.ok,
                last_reading_at=NOW,
                temperature_c=21.0,
            ),
            Event(
                id=uuid.uuid4(),
                senior_id=senior.id,
                type=EventType.fall,
                measured_at=NOW,
                call_id=first.id,
            ),
            Incident(
                senior_id=senior.id,
                status=IncidentStatus.resolved,
                reason="r",
                opened_by_call_id=first.id,
                outcome=IncidentOutcome.senior_ok,
                resolved_by=das.id,
                resolved_at=NOW,
            ),
            CallTurn(
                call_id=first.id,
                position=0,
                speaker=Speaker.senior,
                kind=TurnKind.speech,
                content="Bine.",
            ),
            Answer(
                call_id=first.id,
                field=Question.feeling,
                value="bine",
                clear=True,
                quote="Bine.",
            ),
            StatusReport(
                call_id=second.id,
                source=ReportSource.rules,
                severity=Severity.green,
                reason="r",
            ),
            SeniorStatus(
                senior_id=senior.id,
                code=Severity.green,
                reason="r",
                since=NOW,
                source_call_id=second.id,
            ),
            MedicalRecord(
                senior_id=senior.id,
                storage_key=f"medical-records/{senior.id}/x.pdf",
                uploaded_by=senior.medic_id,
            ),
            PushToken(user_id=caregiver.id, token="caregiver-device"),
        ]
    )
    await db.commit()
    senior_id, medic_id, call_ids = senior.id, senior.medic_id, [first.id, second.id]
    senior_user = await db.scalar(
        select(User).where(User.phone_e164 == senior.phone_e164)
    )
    senior_user_id, caregiver_id = senior_user.id, caregiver.id

    key = await erase_senior(db, await caller_for(db, das), senior_id)

    assert key == f"medical-records/{senior_id}/x.pdf"
    by_senior = [
        Senior.id == senior_id,
        Consent.senior_id == senior_id,
        SummaryVersion.senior_id == senior_id,
        WatchState.senior_id == senior_id,
        WatchReading.senior_id == senior_id,
        HomeNodeState.senior_id == senior_id,
        Event.senior_id == senior_id,
        Incident.senior_id == senior_id,
        Call.senior_id == senior_id,
        SeniorStatus.senior_id == senior_id,
        MedicalRecord.senior_id == senior_id,
        Grant.senior_id == senior_id,
    ]
    for clause in by_senior:
        assert await count(db, clause.left.table, clause) == 0, clause.left.table
    for model in (CallTurn, Answer, StatusReport):
        assert await count(db, model, model.call_id.in_(call_ids)) == 0, model
    assert await count(db, User, User.id.in_([senior_user_id, caregiver_id])) == 0
    assert await count(db, PushToken, PushToken.user_id == caregiver_id) == 0
    assert await count(db, User, or_(User.id == medic_id, User.id == das.id)) == 2


async def test_erase_by_registering_medic_on_draft(db: AsyncSession, add_senior):
    senior = await add_senior("+40700000101")
    medic = await db.get(User, senior.medic_id)
    assert await erase_senior(db, await caller_for(db, medic), senior.id) is None
    assert await count(db, Senior, Senior.id == senior.id) == 0


async def test_erase_refuses_das_on_draft(db: AsyncSession, add_senior, das: User):
    """A draft is out of DAS's reach (01 §6), so it answers as a missing senior."""
    senior = await add_senior("+40700000101")
    with pytest.raises(HTTPException) as refused:
        await erase_senior(db, await caller_for(db, das), senior.id)
    assert refused.value.status_code == 404
    assert refused.value.detail == {"reason": "not_found"}
    assert await count(db, Senior, Senior.id == senior.id) == 1


async def assert_refused(db, caller, senior_id, reason: str) -> None:
    with pytest.raises(HTTPException) as refused:
        await erase_senior(db, caller, senior_id)
    assert refused.value.status_code == 409
    assert refused.value.detail == {"reason": reason}
    await db.rollback()
    assert await count(db, Senior, Senior.id == senior_id) == 1
    assert await count(db, Call, Call.senior_id == senior_id) == 1


@pytest.mark.parametrize(
    ("state", "trigger"),
    [
        (CallState.ringing, CallTrigger.campaign),
        (CallState.in_progress, CallTrigger.campaign),
        (CallState.ringing, CallTrigger.test),  # call_in_progress() ignores these
    ],
)
async def test_erase_refuses_live_call(
    db: AsyncSession, add_active_senior, das: User, state, trigger
):
    senior = await add_active_senior("+40700000101")
    add_call(db, senior, state=state, trigger=trigger)
    await db.commit()
    await assert_refused(db, await caller_for(db, das), senior.id, "call_live")


async def test_erase_refuses_dialed_queued_call(
    db: AsyncSession, add_active_senior, das: User
):
    senior = await add_active_senior("+40700000101")
    add_call(db, senior, state=CallState.queued, dialed_at=NOW)
    await db.commit()
    await assert_refused(db, await caller_for(db, das), senior.id, "call_live")


async def test_erase_deletes_undialed_queued_call(
    db: AsyncSession, add_active_senior, das: User
):
    senior = await add_active_senior("+40700000101")
    add_call(db, senior, state=CallState.queued)
    await db.commit()
    senior_id = senior.id
    await erase_senior(db, await caller_for(db, das), senior_id)
    assert await count(db, Call, Call.senior_id == senior_id) == 0


@pytest.mark.parametrize("status", [IncidentStatus.open, IncidentStatus.in_progress])
async def test_erase_refuses_open_incident(
    db: AsyncSession, add_active_senior, das: User, status
):
    senior = await add_active_senior("+40700000101")
    call = add_call(db, senior)
    await db.flush()
    db.add(
        Incident(
            senior_id=senior.id, status=status, reason="r", opened_by_call_id=call.id
        )
    )
    await db.commit()
    await assert_refused(db, await caller_for(db, das), senior.id, "incident_open")


async def test_erase_keeps_caregiver_of_another_senior(
    db: AsyncSession, add_user, add_active_senior, das: User
):
    erased = await add_active_senior("+40700000101")
    kept = await add_active_senior("+40700000102")
    caregiver = await add_caregiver(db, add_user, erased, "+40700000201")
    db.add(
        Grant(
            user_id=caregiver.id,
            role=Role.caregiver,
            senior_id=kept.id,
            granted_by=kept.medic_id,
        )
    )
    await db.commit()
    caregiver_id, kept_id = caregiver.id, kept.id

    await erase_senior(db, await caller_for(db, das), erased.id)

    assert await count(db, User, User.id == caregiver_id) == 1
    assert (
        await count(
            db, Grant, Grant.user_id == caregiver_id, Grant.senior_id == kept_id
        )
        == 1
    )


# Races (final review, issue 1): a writer that commits between the guards and the deletes.
# `other` holds an uncommitted write while the erasure runs, then commits.


async def erase_racing(db, caller, senior_id, other_commits):
    task = asyncio.create_task(erase_senior(db, caller, senior_id))
    await asyncio.sleep(0.3)  # the erasure is now waiting on, or past, the other write
    await other_commits()
    return await asyncio.wait_for(task, timeout=5)


async def test_erase_waits_for_a_check_in_being_written(
    db: AsyncSession, add_active_senior, das: User
):
    """A check-in insert in flight must not turn the erasure into a foreign-key 500."""
    senior = await add_active_senior("+40700000101")
    senior_id, caller = senior.id, await caller_for(db, das)
    async with Session() as other:
        other.add(WatchReading(senior_id=senior_id, measured_at=NOW))
        await other.flush()  # holds a key-share lock on the senior until it commits
        await erase_racing(db, caller, senior_id, other.commit)
    assert await count(db, WatchReading, WatchReading.senior_id == senior_id) == 0
    assert await count(db, Senior, Senior.id == senior_id) == 0


async def test_erase_refuses_a_call_being_dialed(
    db: AsyncSession, add_active_senior, das: User
):
    """The scheduler claiming a queued call mid-erasure: the call is live, so 409."""
    senior = await add_active_senior("+40700000101")
    call = add_call(db, senior, state=CallState.queued)
    await db.commit()
    senior_id, call_id, caller = senior.id, call.id, await caller_for(db, das)
    async with Session() as other:
        assert await take_for_dialing(other, call_id, NOW)  # row-locked, uncommitted
        with pytest.raises(HTTPException) as refused:
            await erase_racing(db, caller, senior_id, other.commit)
    assert refused.value.detail == {"reason": "call_live"}
    await db.rollback()
    assert await count(db, Call, Call.id == call_id) == 1


async def test_erase_refuses_a_call_row_being_written(
    db: AsyncSession, add_active_senior, das: User
):
    """A hand-over callback writing a turn on a finished call holds its row: the
    erasure answers call_live at once instead of waiting, which could deadlock."""
    senior = await add_active_senior("+40700000101")
    call = add_call(db, senior, state=CallState.handed_over)
    await db.commit()
    senior_id, call_id, caller = senior.id, call.id, await caller_for(db, das)
    async with Session() as other:
        assert await append_turn(other, call_id, Speaker.agent, TurnKind.speech, "Da")
        with pytest.raises(HTTPException) as refused:
            await asyncio.wait_for(erase_senior(db, caller, senior_id), timeout=5)
        await other.rollback()
    assert refused.value.detail == {"reason": "call_live"}
    await db.rollback()
    assert await count(db, Senior, Senior.id == senior_id) == 1


async def test_erase_keeps_a_caregiver_still_named_elsewhere(
    db: AsyncSession, add_user, add_senior, add_active_senior, das: User
):
    """A former medic, now only a caregiver, still registered another senior: their
    user row stays, and the erasure goes through instead of a foreign-key 500."""
    erased = await add_active_senior("+40700000101")
    former_medic = await add_caregiver(db, add_user, erased, "+40700000201")
    await add_senior("+40700000102", medic=former_medic)
    former_id = former_medic.id

    await erase_senior(db, await caller_for(db, das), erased.id)

    assert await count(db, Senior, Senior.id == erased.id) == 0
    assert await count(db, User, User.id == former_id) == 1


# Every table besides `seniors` that points at a senior or a call, or names one by
# column. A new one
# fails here until erase_senior deletes its rows and this list names it.
ERASED_TABLES = {
    "grants",
    "consents",
    "senior_summaries",
    "watch_states",
    "watch_readings",
    "home_node_states",
    "events",
    "incidents",
    "calls",
    "call_turns",
    "answers",
    "status_reports",
    "senior_statuses",
    "medical_records",
}


def test_every_senior_table_is_erased():
    about_a_senior = {
        table.name
        for table in Base.metadata.sorted_tables
        if {"senior_id", "call_id"} & set(table.columns.keys())
        or any(
            fk.column.table.name in ("seniors", "calls") for fk in table.foreign_keys
        )
    }
    assert about_a_senior == ERASED_TABLES
