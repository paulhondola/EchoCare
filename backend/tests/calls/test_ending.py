"""The shared step that ends a call into a code and an incident (design §5, 03 §6, §8)."""

from datetime import UTC, date, datetime, timedelta
from itertools import count
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.calls.ending import (
    campaign_reason,
    conclude,
    conclude_welcome,
    redial_delay,
)
from app.models import (
    Call,
    CallTrigger,
    Campaign,
    CampaignKind,
    Consent,
    ConsentMethod,
    EnrollmentState,
    Incident,
    IncidentStatus,
    Senior,
    SeniorStatus,
    WarningLevel,
)
from app.status.engine import Answer, CallAnswers, Certainty, Question, Severity
from app.voice.calls import CallState


def answers(feeling: str, day: str, shelter: str) -> CallAnswers:
    """All three questions answered, every one clear."""
    return CallAnswers(
        {
            Question.feeling: Answer(feeling, True, feeling),
            Question.orientation: Answer(day, True, day),
            Question.shelter: Answer(shelter, True, shelter),
        }
    )


@pytest.fixture(autouse=True)
def thursday(monkeypatch):
    monkeypatch.setattr(
        "app.calls.ending.today_in_bucharest", lambda: date(2026, 10, 15)
    )


@pytest.fixture
def campaign_call(db, add_active_senior):
    """campaign_call(kind=cold, state=in_progress, **columns): one more call of the test's
    one campaign and one active senior, both made on first use. `kind` only counts then."""
    made = {}

    async def make(
        kind: CampaignKind = CampaignKind.cold,
        state: CallState = CallState.in_progress,
        **columns,
    ) -> Call:
        if not made:
            senior = await add_active_senior("+40700000101")
            campaign = Campaign(
                kind=kind,
                level=WarningLevel.yellow,
                started_by=senior.medic_id,
                warning_until=datetime.now(UTC) + timedelta(hours=24),
            )
            db.add(campaign)
            await db.flush()  # the database makes the id
            made["senior"], made["campaign"] = senior, campaign
        call = Call(
            senior_id=made["senior"].id,
            trigger=CallTrigger.campaign,
            campaign_id=made["campaign"].id,
            starting_severity=Severity.green,
            state=state,
            due_at=datetime.now(UTC),
            **columns,
        )
        db.add(call)
        await db.commit()
        return call

    return make


@pytest.fixture
def welcome_call(db, add_senior):
    """welcome_call(state=accepted): a fresh senior in that state, with a welcome call
    in progress."""
    numbers = count(200)

    async def make(state: EnrollmentState = EnrollmentState.accepted) -> Call:
        senior = await add_senior(f"+40700000{next(numbers)}", enrollment_state=state)
        call = Call(
            senior_id=senior.id,
            trigger=CallTrigger.welcome,
            starting_severity=Severity.green,
            state=CallState.in_progress,
            due_at=datetime.now(UTC),
        )
        db.add(call)
        await db.commit()
        return call

    return make


@pytest.mark.parametrize(
    ("worrying", "kind", "reason"),
    [
        (
            [],
            CampaignKind.cold,
            "Se simte bine, știe ce zi este și are căldură",
        ),
        (
            [],
            CampaignKind.heat,
            "Se simte bine, știe ce zi este și are un loc răcoros",
        ),
        ([Question.feeling], CampaignKind.cold, "Se simte rău"),
        ([Question.orientation], CampaignKind.heat, "Nu știe ce zi este"),
        (
            [Question.feeling, Question.shelter],
            CampaignKind.cold,
            "Se simte rău și nu are căldură în casă",
        ),
        (
            [Question.feeling, Question.orientation, Question.shelter],
            CampaignKind.heat,
            "Se simte rău, nu știe ce zi este și nu are un loc răcoros",
        ),
    ],
)
def test_the_reason_names_what_is_worrying(worrying, kind, reason):
    assert campaign_reason(worrying, kind) == reason


def test_the_redial_waits_20_minutes_or_20_seconds_in_demo_mode(monkeypatch):
    monkeypatch.setattr(
        "app.calls.ending.get_settings", lambda: SimpleNamespace(demo_mode=False)
    )
    assert redial_delay() == timedelta(minutes=20)
    monkeypatch.setattr(
        "app.calls.ending.get_settings", lambda: SimpleNamespace(demo_mode=True)
    )
    assert redial_delay() == timedelta(seconds=20)


async def test_clear_fine_answers_end_green(db, campaign_call):
    call = await campaign_call()
    assert await conclude(db, call, answers("ok", "joi", "yes")) is Severity.green
    await db.commit()
    assert (call.state, call.final_certainty, call.reason) == (
        CallState.completed,
        Certainty.high,
        "Se simte bine, știe ce zi este și are căldură",
    )
    status = await db.get(SeniorStatus, call.senior_id)
    assert (status.code, status.source_call_id) == (Severity.green, call.id)
    assert await db.scalar(select(func.count()).select_from(Incident)) == 0


async def test_unwell_and_no_heating_is_red_with_an_incident(db, campaign_call):
    call = await campaign_call()
    assert await conclude(db, call, answers("unwell", "joi", "no")) is Severity.red
    await db.commit()
    incident = await db.scalar(select(Incident))
    assert (incident.status, incident.opened_by_call_id, incident.reason) == (
        IncidentStatus.open,
        call.id,
        "Se simte rău și nu are căldură în casă",
    )


async def test_a_wrong_day_alone_is_yellow(db, campaign_call):
    call = await campaign_call()
    assert await conclude(db, call, answers("ok", "luni", "yes")) is Severity.yellow


async def test_heat_wording(db, campaign_call):
    call = await campaign_call(kind=CampaignKind.heat)
    await conclude(db, call, answers("ok", "joi", "no"))
    assert call.reason == "Nu are un loc răcoros"


async def test_a_red_with_an_open_incident_is_not_lowered(db, campaign_call):
    call = await campaign_call()
    db.add_all(
        [
            SeniorStatus(
                senior_id=call.senior_id,
                code=Severity.red,
                reason="r",
                since=datetime.now(UTC),
            ),
            Incident(senior_id=call.senior_id, reason="r"),
        ]
    )
    await conclude(db, call, answers("ok", "joi", "yes"))
    await db.commit()
    status = await db.get(SeniorStatus, call.senior_id, populate_existing=True)
    assert status.code is Severity.red


async def test_a_first_no_answer_queues_a_redial(db, campaign_call, monkeypatch):
    monkeypatch.setattr(
        "app.calls.ending.get_settings", lambda: SimpleNamespace(demo_mode=True)
    )
    call = await campaign_call(state=CallState.unanswered)
    assert await conclude(db, call, None) is None
    await db.commit()
    redial = await db.scalar(select(Call).where(Call.previous_call_id == call.id))
    assert (redial.attempt, redial.state, redial.campaign_id) == (
        2,
        CallState.queued,
        call.campaign_id,
    )
    assert (
        timedelta(seconds=15)
        < redial.due_at - datetime.now(UTC)
        <= timedelta(seconds=20)
    )
    assert await db.get(SeniorStatus, call.senior_id) is None


async def test_a_second_no_answer_is_yellow(db, campaign_call):
    first = await campaign_call(state=CallState.unanswered)
    second = await campaign_call(
        state=CallState.unanswered, attempt=2, previous_call_id=first.id
    )
    assert await conclude(db, second, None) is Severity.yellow
    assert second.reason == "Nu a răspuns de două ori"


async def test_welcome_consent_activates_with_a_green_code(db, welcome_call):
    call = await welcome_call()
    assert await conclude_welcome(
        db, call, given=True, method=ConsentMethod.app, text_version="v1-app"
    )
    await db.commit()
    senior = await db.get(Senior, call.senior_id, populate_existing=True)
    consent = await db.scalar(select(Consent))
    assert (senior.enrollment_state, consent.method, consent.text_version) == (
        EnrollmentState.active,
        ConsentMethod.app,
        "v1-app",
    )
    assert (await db.get(SeniorStatus, senior.id)).reason == "Consimțământ dat"


async def test_welcome_refusal_and_a_senior_no_longer_accepted(db, welcome_call):
    refused = await welcome_call()
    assert await conclude_welcome(
        db, refused, given=False, method=ConsentMethod.app, text_version="v1-app"
    )
    late = await welcome_call(state=EnrollmentState.withdrawn)
    assert not await conclude_welcome(
        db, late, given=True, method=ConsentMethod.app, text_version="v1-app"
    )
