"""Call again: POST /seniors/{id}/welcome-call, Sună din nou (#54, UC-04, 04 §2)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.calls.ending import close_welcome
from app.models import (
    Call,
    CallTrigger,
    EnrollmentState,
    Grant,
    Role,
    Senior,
    WelcomeOutcome,
)
from app.status.engine import Severity
from app.voice.calls import CallState
from tests.seniors.test_enrollments import (
    CAREGIVER,
    DAS,
    MEDIC,
    NOT_ALLOWED,
    NOT_FOUND,
    OTHER_MEDIC,
    WRONG_STATE,
    refusal,
    signed_in,
)

SENIOR = "+40700000105"
HER_PHONE = "+40700000106"  # the senior of `senior_card`


@pytest.fixture
async def staff(add_user):
    await add_user(DAS, Role.das, name="DAS Test")
    await add_user(OTHER_MEDIC, Role.medic, name="Dr. Alt")
    return await add_user(MEDIC, Role.medic, name="Dr. Pop")


@pytest.fixture
async def senior_in(db, add_senior, staff):
    """senior_in(state): her medic's senior, in that state, accepted a day ago."""

    async def make(state: EnrollmentState) -> Senior:
        senior = await add_senior(
            SENIOR,
            medic=staff,
            enrollment_state=state,
            accepted_at=datetime.now(UTC) - timedelta(days=1),
        )
        return senior

    return make


async def call_again(client, senior_id, token=MEDIC):
    return await client.post(
        f"/api/seniors/{senior_id}/welcome-call", headers=signed_in(token)
    )


async def welcome_calls(db) -> list[Call]:
    await db.rollback()  # a fresh read
    rows = await db.scalars(select(Call).where(Call.trigger == CallTrigger.welcome))
    return list(rows)


@pytest.mark.parametrize(
    "state", [EnrollmentState.unreachable, EnrollmentState.wrong_number]
)
async def test_call_again_queues_a_welcome_call(client, db, senior_in, state):
    senior = await senior_in(state)
    accepted_at = senior.accepted_at
    before = datetime.now(UTC)
    r = await call_again(client, senior.id)
    assert r.status_code == 200, r.text
    assert r.json()["enrollment_state"] == "accepted"
    assert datetime.fromisoformat(r.json()["accepted_at"]) == accepted_at
    (call,) = await welcome_calls(db)
    assert (call.state, call.attempt) == (CallState.queued, 1)
    assert before - timedelta(seconds=1) <= call.due_at <= datetime.now(UTC)


async def test_call_again_with_the_same_number(client, db, senior_in):
    """The number is not checked: a correct one can come back as wrong_number."""
    senior = await senior_in(EnrollmentState.wrong_number)
    assert (await call_again(client, senior.id)).status_code == 200
    assert len(await welcome_calls(db)) == 1


async def test_a_repeat_answers_the_same(client, db, senior_in):
    senior = await senior_in(EnrollmentState.unreachable)
    first = await call_again(client, senior.id)
    second = await call_again(client, senior.id)
    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == second.json()
    assert len(await welcome_calls(db)) == 1


async def test_accepted_without_a_pending_call_is_wrong_state(client, db, senior_in):
    senior = await senior_in(EnrollmentState.accepted)
    assert refusal(await call_again(client, senior.id)) == WRONG_STATE
    assert await welcome_calls(db) == []


@pytest.mark.parametrize(
    "state",
    [
        EnrollmentState.draft,
        EnrollmentState.submitted,
        EnrollmentState.active,
        EnrollmentState.refused,
        EnrollmentState.withdrawn,
    ],
)
async def test_other_states_are_wrong_state(client, db, senior_in, state):
    senior = await senior_in(state)
    assert refusal(await call_again(client, senior.id)) == WRONG_STATE
    assert await welcome_calls(db) == []


async def test_another_live_call_keeps_her_where_she_is(client, db, senior_in):
    """A live call leaves no room for the welcome call (05 §3): no move without one."""
    senior = await senior_in(EnrollmentState.unreachable)
    db.add(
        Call(
            senior_id=senior.id,
            trigger=CallTrigger.test,
            starting_severity=Severity.green,
            due_at=datetime.now(UTC),
        )
    )
    await db.commit()
    assert refusal(await call_again(client, senior.id)) == WRONG_STATE
    assert await welcome_calls(db) == []
    await db.refresh(senior)
    assert senior.enrollment_state == EnrollmentState.unreachable


async def test_only_her_medic(client, db, add_user, senior_in):
    senior = await senior_in(EnrollmentState.unreachable)
    caregiver = await add_user(CAREGIVER)
    db.add(Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=senior.id))
    await db.commit()
    assert refusal(await call_again(client, senior.id, OTHER_MEDIC)) == NOT_FOUND
    assert refusal(await call_again(client, senior.id, DAS)) == NOT_ALLOWED
    assert (await call_again(client, senior.id, CAREGIVER)).status_code == 403
    assert await welcome_calls(db) == []
    assert (await call_again(client, senior.id)).status_code == 200


async def test_the_card_offers_it_again(client, db, add_user, senior_in):
    senior = await senior_in(EnrollmentState.unreachable)
    herself = await add_user(HER_PHONE, name="Maria Pop")
    db.add(Grant(user_id=herself.id, role=Role.senior, senior_id=senior.id))
    await db.commit()
    token = signed_in(HER_PHONE)
    assert (
        await client.get("/api/profile/mock-call", headers=token)
    ).status_code == 204
    assert (await call_again(client, senior.id)).status_code == 200
    r = await client.get("/api/profile/mock-call", headers=token)
    assert r.status_code == 200
    assert r.json()["trigger"] == "welcome"
    (call,) = await welcome_calls(db)
    assert r.json()["call_id"] == str(call.id)


async def test_a_second_round_ends_unreachable_again(client, db, senior_in):
    senior = await senior_in(EnrollmentState.unreachable)
    assert (await call_again(client, senior.id)).status_code == 200
    for attempt in (1, 2):
        (call,) = [c for c in await welcome_calls(db) if c.state is CallState.queued]
        assert call.attempt == attempt
        await db.execute(
            update(Call).where(Call.id == call.id).values(state=CallState.in_progress)
        )
        await db.commit()
        await db.refresh(call)
        assert await close_welcome(db, call, WelcomeOutcome.no_answer)
        await db.commit()
    await db.refresh(senior)
    assert senior.enrollment_state == EnrollmentState.unreachable
