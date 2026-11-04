"""The shared step that ends a call into a code and an incident (design §5, 03 §6, §8)."""

from datetime import UTC, date, datetime, timedelta
from itertools import count
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.calls.ending import (
    begin_handover,
    campaign_reason,
    close_welcome,
    conclude,
    conclude_welcome,
    redial_delay,
    settle,
)
from app.core.changes import Change, ChangeKind, take_notes
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
    ReportSource,
    Senior,
    SeniorStatus,
    StatusReport,
    WarningLevel,
    WelcomeOutcome,
)
from app.status.engine import Answer, CallAnswers, Certainty, Question, Severity
from app.voice.calls import CallState
from tests.voice.test_voice import FIXTURES, SID, callback, stored


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
    """welcome_call(state=accepted, call_state=in_progress, **columns): a fresh senior in
    that state, with a welcome call."""
    numbers = count(200)

    async def make(
        state: EnrollmentState = EnrollmentState.accepted,
        call_state: CallState = CallState.in_progress,
        **columns,
    ) -> Call:
        senior = await add_senior(f"+40700000{next(numbers)}", enrollment_state=state)
        call = Call(
            senior_id=senior.id,
            trigger=CallTrigger.welcome,
            starting_severity=Severity.green,
            state=call_state,
            due_at=datetime.now(UTC),
            **columns,
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


async def test_a_red_joining_a_yellow_incident_is_noted_for_das(db, campaign_call):
    """G16 opens none, but 04 §6 still tells every DAS phone."""
    call = await campaign_call()
    incident = Incident(senior_id=call.senior_id, reason="r")
    db.add_all(
        [
            SeniorStatus(
                senior_id=call.senior_id,
                code=Severity.yellow,
                reason="r",
                since=datetime.now(UTC),
            ),
            incident,
        ]
    )
    await db.flush()
    take_notes(db)
    assert await conclude(db, call, answers("unwell", "joi", "no")) is Severity.red
    assert Change(
        ChangeKind.incident_raised, call.senior_id, incident.id
    ) in take_notes(db)


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


# The phone's welcome call: its endings, the retry and `unreachable` (#48, UC-04).


async def senior_of(db, call) -> Senior:
    return await db.get(Senior, call.senior_id, populate_existing=True)


async def test_a_call_consent_keeps_its_evidence(db, welcome_call):
    call = await welcome_call()
    assert await conclude_welcome(
        db,
        call,
        given=True,
        method=ConsentMethod.call,
        text_version="v1",
        evidence={"digits": "1"},
    )
    await db.commit()
    consent = await db.scalar(select(Consent))
    assert (consent.method, consent.text_version, consent.evidence) == (
        ConsentMethod.call,
        "v1",
        {"digits": "1"},
    )
    assert (await senior_of(db, call)).enrollment_state == EnrollmentState.active
    assert (await db.get(SeniorStatus, call.senior_id)).code == Severity.green


async def test_wrong_number_ends_the_welcome(db, welcome_call):
    call = await welcome_call()
    assert await close_welcome(db, call, WelcomeOutcome.wrong_number)
    await db.commit()
    row = await stored(db, call)
    assert (row.state, row.welcome_outcome) == (
        CallState.completed,
        WelcomeOutcome.wrong_number,
    )
    assert (await senior_of(db, call)).enrollment_state == EnrollmentState.wrong_number
    assert await redials(db, call) == []


@pytest.mark.parametrize(
    "outcome",
    [WelcomeOutcome.not_available, WelcomeOutcome.no_answer, WelcomeOutcome.confirmed],
)
async def test_a_first_welcome_that_gets_nowhere_is_retried(db, welcome_call, outcome):
    call = await welcome_call()
    before = datetime.now(UTC)
    assert await close_welcome(db, call, outcome)
    await db.commit()
    row = await stored(db, call)
    assert (row.state, row.welcome_outcome) == (CallState.completed, outcome)
    (retry,) = await redials(db, call)
    assert (retry.trigger, retry.attempt, retry.state) == (
        CallTrigger.welcome,
        2,
        CallState.queued,
    )
    assert before + redial_delay() <= retry.due_at <= datetime.now(UTC) + redial_delay()
    assert (await senior_of(db, call)).enrollment_state == EnrollmentState.accepted


async def test_a_second_welcome_that_gets_nowhere_makes_the_senior_unreachable(
    db, welcome_call
):
    call = await welcome_call(attempt=2)
    assert await close_welcome(db, call, WelcomeOutcome.no_answer)
    await db.commit()
    assert (await senior_of(db, call)).enrollment_state == EnrollmentState.unreachable
    assert await redials(db, call) == []


async def test_closing_an_ended_welcome_changes_nothing(db, welcome_call):
    call = await welcome_call(call_state=CallState.completed)
    assert not await close_welcome(db, call, WelcomeOutcome.no_answer)
    await db.commit()
    assert (await stored(db, call)).welcome_outcome is None
    assert await redials(db, call) == []


async def test_a_withdrawn_senior_is_left_as_they_are(db, welcome_call):
    call = await welcome_call(state=EnrollmentState.withdrawn, attempt=2)
    assert await close_welcome(db, call, WelcomeOutcome.no_answer)
    await db.commit()
    assert (await senior_of(db, call)).enrollment_state == EnrollmentState.withdrawn


# `settle`: Twilio's word on a real call runs the redial rule (design §6, 06 §1).


async def twilio_says(client, call, twilio_status, sid=SID):
    params = {**FIXTURES["status_common"], "CallStatus": twilio_status, "CallSid": sid}
    return await callback(client, "status", call.id, params)


async def redials(db, call) -> list[Call]:
    rows = await db.scalars(select(Call).where(Call.previous_call_id == call.id))
    return list(rows)


async def test_no_answer_on_a_first_attempt_queues_the_redial(
    client, db, campaign_call
):
    call = await campaign_call(state=CallState.ringing)
    assert (await twilio_says(client, call, "no-answer")).status_code == 204
    assert (await stored(db, call)).state == CallState.unanswered
    (redial,) = await redials(db, call)
    assert (redial.attempt, redial.state) == (2, CallState.queued)
    assert (
        redial_delay() - timedelta(seconds=15)
        < redial.due_at - datetime.now(UTC)
        <= redial_delay()
    )


async def test_busy_on_a_second_attempt_ends_yellow(client, db, campaign_call):
    first = await campaign_call(state=CallState.unanswered)
    second = await campaign_call(
        state=CallState.ringing, attempt=2, previous_call_id=first.id
    )
    await twilio_says(client, second, "busy")
    row = await stored(db, second)
    assert (row.state, row.final_severity, row.reason) == (
        CallState.unanswered,
        Severity.yellow,
        "Nu a răspuns de două ori",
    )
    assert await redials(db, second) == []


async def test_failed_counts_as_unanswered(client, db, campaign_call):
    call = await campaign_call(state=CallState.ringing)
    await twilio_says(client, call, "failed")
    assert (await stored(db, call)).state == CallState.failed
    (redial,) = await redials(db, call)
    assert redial.attempt == 2


async def test_a_repeated_no_answer_queues_one_redial(client, db, campaign_call):
    call = await campaign_call(state=CallState.ringing)
    await twilio_says(client, call, "no-answer")
    await twilio_says(client, call, "no-answer")
    assert len(await redials(db, call)) == 1


async def test_voicemail_queues_the_redial_and_hangs_up(
    client, db, campaign_call, monkeypatch
):
    hung_up = []

    async def fake_hang_up(sid):
        hung_up.append(sid)

    monkeypatch.setattr("app.voice.router.hang_up", fake_hang_up)
    call = await campaign_call(state=CallState.in_progress)
    r = await callback(client, "amd", call.id, FIXTURES["amd_machine"])
    assert r.status_code == 204
    assert (await stored(db, call)).state == CallState.unanswered
    assert len(await redials(db, call)) == 1
    assert hung_up == [SID]


@pytest.mark.parametrize(
    ("call_state", "twilio_status", "ended"),
    [
        (CallState.ringing, "no-answer", CallState.unanswered),
        (CallState.ringing, "failed", CallState.failed),
        # a hang-up partway through the script (design §2)
        (CallState.in_progress, "completed", CallState.dropped),
    ],
)
async def test_a_welcome_twilio_ends_runs_the_retry_rule(
    client, db, welcome_call, call_state, twilio_status, ended
):
    call = await welcome_call(call_state=call_state)
    await twilio_says(client, call, twilio_status)
    row = await stored(db, call)
    assert (row.state, row.welcome_outcome) == (ended, WelcomeOutcome.no_answer)
    (retry,) = await redials(db, call)
    assert retry.attempt == 2
    assert await db.scalar(select(func.count()).select_from(StatusReport)) == 0


async def test_a_test_call_is_still_never_concluded(client, db, welcome_call):
    call = await welcome_call(call_state=CallState.ringing)
    call.trigger = CallTrigger.test
    await db.commit()
    await twilio_says(client, call, "no-answer")
    row = await stored(db, call)
    assert (row.state, row.welcome_outcome) == (CallState.unanswered, None)
    assert await redials(db, call) == []
    assert await db.scalar(select(func.count()).select_from(StatusReport)) == 0


async def test_only_from_leaves_a_call_that_moved_on(db, campaign_call):
    call = await campaign_call(state=CallState.ringing)
    moved = await settle(
        db, call.id, None, CallState.failed, only_from=CallState.queued
    )
    assert moved is None
    assert (await stored(db, call)).state == CallState.ringing


# `begin_handover`: key 9 or a tier 1 phrase, written before the session ends (#48, §4).


@pytest.fixture
def live_call(db, add_active_senior):
    """live_call(code=None, incident=False): a manual call in progress for an active
    senior, with that code and an open incident if asked."""

    async def make(code: Severity | None = None, incident: bool = False) -> Call:
        senior = await add_active_senior("+40700000301")
        call = Call(
            senior_id=senior.id,
            trigger=CallTrigger.manual,
            starting_severity=Severity.yellow,
            state=CallState.in_progress,
            due_at=datetime.now(UTC),
        )
        db.add(call)
        await db.flush()
        if code is not None:
            db.add(
                SeniorStatus(
                    senior_id=senior.id,
                    code=code,
                    reason="Înainte",
                    since=datetime.now(UTC),
                    source_call_id=call.id,
                )
            )
        if incident:
            db.add(
                Incident(
                    senior_id=senior.id,
                    status=IncidentStatus.open,
                    opened_by_call_id=call.id,
                    reason="Înainte",
                )
            )
        await db.commit()
        return call

    return make


async def code_of(db, call) -> SeniorStatus:
    return await db.get(SeniorStatus, call.senior_id, populate_existing=True)


async def incidents_of(db, call) -> list[Incident]:
    rows = await db.scalars(
        select(Incident)
        .where(Incident.senior_id == call.senior_id)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def test_key_9_on_a_green_senior(db, live_call):
    call = await live_call(code=Severity.green)
    reason = "A cerut un operator (tasta 9)"
    assert await begin_handover(call.id, ReportSource.request_human, reason)
    status = await code_of(db, call)
    assert (status.code, status.reason) == (Severity.yellow, reason)
    report = await db.scalar(select(StatusReport))
    assert (report.source, report.severity) == (
        ReportSource.request_human,
        Severity.yellow,
    )
    (incident,) = await incidents_of(db, call)
    assert (incident.status, incident.opened_by_call_id, incident.reason) == (
        IncidentStatus.open,
        call.id,
        reason,
    )
    row = await stored(db, call)
    assert (row.state, row.final_severity, row.reason) == (
        CallState.handed_over,
        Severity.yellow,
        reason,
    )


async def test_key_9_on_a_red_senior_joins_the_incident(db, live_call):
    call = await live_call(code=Severity.red, incident=True)
    assert await begin_handover(
        call.id, ReportSource.request_human, "A cerut un operator (tasta 9)"
    )
    status = await code_of(db, call)
    assert (status.code, status.reason) == (Severity.red, "Înainte")
    assert len(await incidents_of(db, call)) == 1


async def test_tier_1_makes_red_and_opens_an_incident(db, live_call):
    call = await live_call()
    reason = "A spus: «am căzut și nu mă pot ridica»"
    assert await begin_handover(call.id, ReportSource.alarm_tier1, reason)
    assert (await code_of(db, call)).code == Severity.red
    (incident,) = await incidents_of(db, call)
    assert incident.reason == reason
    assert (await stored(db, call)).final_severity == Severity.red


async def test_a_second_hand_over_is_a_no_op(db, live_call):
    call = await live_call()
    reason = "A cerut un operator (tasta 9)"
    assert await begin_handover(call.id, ReportSource.request_human, reason)
    assert not await begin_handover(call.id, ReportSource.request_human, reason)
    assert await db.scalar(select(func.count()).select_from(StatusReport)) == 1
    assert len(await incidents_of(db, call)) == 1
