import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth.models import User
from app.auth.service import refuse
from app.codes.models import StatusReport
from app.core.changes import Change, ChangeKind, note
from app.core.db import engine
from app.incidents.models import UNRESOLVED, Event, Incident, IncidentStatus
from app.incidents.schemas import (
    CallDetail,
    EventForm,
    EventView,
    IncidentDetail,
    IncidentSummary,
    ReportView,
    ResolutionForm,
    TriggerEventView,
    TurnView,
)
from app.seniors.models import EnrollmentState, Senior
from app.seniors.schemas import CaregiverSummary, SeniorDetail
from app.seniors.service import caregivers_query, latest_summary, summary_view
from app.status.engine import Severity
from app.voice.models import Call, CallTrigger, CallTurn
from app.voice.service import queue_calls, recent_call

log = logging.getLogger("echocare.incidents")

# An event measured longer ago than this starts no call (04 §3, 06 §3).
STALE = timedelta(minutes=30)


async def record_event(
    session: AsyncSession, senior_id: uuid.UUID, form: EventForm, now: datetime
) -> EventView:
    """Stores the senior's „Sunați-mă” and applies the intake rules (UC-10, 04 §3): a
    resent id is ignored; a stale event, or one for a senior who is not `active`, is
    recorded and starts no call; otherwise the event joins the call queued, live or just
    ended, or queues a yellow one.
    """
    stored = await session.scalar(
        insert(Event)
        .values(
            id=form.id,
            senior_id=senior_id,
            type=form.type,
            measured_at=form.measured_at,
            source=form.source,
            snapshot=(
                form.snapshot.model_dump(exclude_none=True) if form.snapshot else None
            ),
            latitude=form.latitude,
            longitude=form.longitude,
            location_accuracy_m=form.location_accuracy_m,
            located_at=now if form.latitude is not None else None,
        )
        .on_conflict_do_nothing()
        .returning(Event.id)
    )
    if stored is None:
        call_id = await session.scalar(
            select(Event.call_id).where(
                Event.id == form.id, Event.senior_id == senior_id
            )
        )
        return EventView(queued=False, call_id=call_id)

    senior = await session.get(Senior, senior_id)
    call_id, queued = None, False
    if (
        senior is not None
        and senior.enrollment_state is EnrollmentState.active
        and now - form.measured_at <= STALE
    ):
        call = await recent_call(session, senior_id, now)
        if call is None:
            await queue_calls(
                session,
                Senior.id == senior_id,
                trigger=CallTrigger.manual,
                due_at=now,
                starting_severity=Severity.yellow,
            )
            call, queued = await recent_call(session, senior_id, now), True
        call_id = call.id
        await session.execute(
            update(Event).where(Event.id == form.id).values(call_id=call_id)
        )
    await session.commit()
    return EventView(queued=queued, call_id=call_id)


def opens_incident(result: Severity, unresolved: bool) -> bool:
    """Whether a call's result opens a new incident (G16).

    A later red while one is open or in progress is added to that one, through the call.
    """
    return result is Severity.red and not unresolved


def open_incident(
    session: AsyncSession, senior_id: uuid.UUID, call_id: uuid.UUID, reason: str
) -> None:
    """The incident a call's red opens; `opens_incident` decides whether (G16).
    Doesn't commit (ADR-005)."""
    # Its id made here, not by the database, so the push can name it (04 §6)
    incident_id = uuid.uuid7()
    session.add(
        Incident(
            id=incident_id,
            senior_id=senior_id,
            status=IncidentStatus.open,
            opened_by_call_id=call_id,
            reason=reason,
        )
    )
    note(session, Change(ChangeKind.incident_opened, senior_id, incident_id))


async def note_red_added(
    session: AsyncSession,
    senior_id: uuid.UUID,
    severity: Severity,
    before: Severity | None,
) -> None:
    """A red added to the unresolved incident (G16) that was not red before: DAS hears of
    it (04 §6). Red again adds nothing to say (P5). Doesn't commit (ADR-005)."""
    if severity is not Severity.red or before is Severity.red:
        return
    incident_id = await session.scalar(
        select(Incident.id).where(
            Incident.senior_id == senior_id, Incident.status.in_(UNRESOLVED)
        )
    )
    if incident_id is not None:
        note(session, Change(ChangeKind.incident_raised, senior_id, incident_id))


def take_refusal(
    status: IncidentStatus, taken_by: uuid.UUID | None, caller: uuid.UUID
) -> str | None:
    """Why POST /incidents/{id}/take is refused, once its update changed nothing (04 §2).

    None for the person who already has it: a repeated command has no second effect
    (04 §0). Anyone else is told who has it.
    """
    if status is IncidentStatus.resolved:
        return "wrong_state"
    if status is IncidentStatus.in_progress and taken_by != caller:
        return "already_done"
    return None


def resolve_refusal(
    status: IncidentStatus,
    done: tuple[uuid.UUID | None, str | None, str | None],
    wanted: tuple[uuid.UUID, str, str],
) -> str | None:
    """Why POST /incidents/{id}/resolve is refused, once its update changed nothing.

    An open incident is taken first (UC-11). Any DAS employee may resolve one in
    progress, so a shift change needs no hand-back. `done` and `wanted` are who, the
    outcome and the note; None only for an exact repeat (04 §2).
    """
    if status is IncidentStatus.open:
        return "wrong_state"
    if status is IncidentStatus.resolved and done != wanted:
        return "already_done"
    return None


def incident_query(incident_id: uuid.UUID) -> Select:
    taker, resolver = aliased(User), aliased(User)
    return (
        select(
            Incident,
            Senior,
            taker.display_name.label("taken_by_name"),
            resolver.display_name.label("resolved_by_name"),
        )
        .join(Senior, Senior.id == Incident.senior_id)
        .outerjoin(taker, taker.id == Incident.taken_by)
        .outerjoin(resolver, resolver.id == Incident.resolved_by)
        .where(Incident.id == incident_id)
    )


def calls_query(
    senior_id: uuid.UUID, since: datetime, until: datetime | None
) -> Select:
    """The senior's calls in the incident's window, oldest first."""
    query = select(Call).where(Call.senior_id == senior_id, Call.created_at >= since)
    if until is not None:
        query = query.where(Call.created_at <= until)
    return query.order_by(Call.created_at, Call.attempt)


async def attempts_behind(session: AsyncSession, call_id: uuid.UUID) -> list[Call]:
    """The opening call and the attempts it redialled, newest first (03 §9)."""
    chain: list[Call] = []
    next_id: uuid.UUID | None = call_id
    # A redial chain is a couple of attempts long; the bound guards a bad row.
    while next_id is not None and len(chain) < 10:
        call = await session.get(Call, next_id)
        if call is None:
            break
        chain.append(call)
        next_id = call.previous_call_id
    return chain


async def load_incident(
    session: AsyncSession, incident_id: uuid.UUID
) -> IncidentDetail | None:
    row = (await session.execute(incident_query(incident_id))).one_or_none()
    if row is None:
        return None
    incident, senior = row.Incident, row.Senior

    chain = (
        await attempts_behind(session, incident.opened_by_call_id)
        if incident.opened_by_call_id
        else []
    )
    since = chain[-1].created_at if chain else incident.opened_at
    calls = list(
        (
            await session.scalars(calls_query(senior.id, since, incident.resolved_at))
        ).all()
    )
    call_ids = [c.id for c in calls]

    turns: dict[uuid.UUID, list[TurnView]] = {i: [] for i in call_ids}
    reports: dict[uuid.UUID, list[ReportView]] = {i: [] for i in call_ids}
    if call_ids:
        for t in await session.scalars(
            select(CallTurn)
            .where(CallTurn.call_id.in_(call_ids))
            .order_by(CallTurn.call_id, CallTurn.position)
        ):
            turns[t.call_id].append(TurnView.model_validate(t, from_attributes=True))
        for r in await session.scalars(
            select(StatusReport)
            .where(StatusReport.call_id.in_(call_ids))
            .order_by(StatusReport.at)
        ):
            reports[r.call_id].append(
                ReportView.model_validate(r, from_attributes=True)
            )

    event = (
        await session.scalar(
            select(Event)
            .where(Event.call_id.in_([c.id for c in chain]))
            .order_by(Event.received_at)
            .limit(1)
        )
        if chain
        else None
    )
    caregivers = (await session.execute(caregivers_query(senior.id))).mappings()

    return IncidentDetail(
        id=incident.id,
        status=incident.status,
        reason=incident.reason,
        opened_at=incident.opened_at,
        taken_by_name=row.taken_by_name,
        taken_at=incident.taken_at,
        resolved_by_name=row.resolved_by_name,
        resolved_at=incident.resolved_at,
        outcome=incident.outcome,
        note=incident.note,
        # A later red added to the incident may be the one whose hand-over was answered.
        handover_answered=any(c.handover_answered for c in calls),
        senior=SeniorDetail.model_validate(senior, from_attributes=True),
        caregivers=[CaregiverSummary.model_validate(dict(c)) for c in caregivers],
        event=event and TriggerEventView.model_validate(event, from_attributes=True),
        calls=[call_detail(c, reports[c.id], turns[c.id]) for c in calls],
        summary=summary_view(await latest_summary(session, senior.id)),
    )


def call_detail(
    call: Call, reports: list[ReportView], turns: list[TurnView]
) -> CallDetail:
    columns = CallDetail.model_fields.keys() - {"reports", "turns"}
    fields = {name: getattr(call, name) for name in columns}
    return CallDetail.model_validate({**fields, "reports": reports, "turns": turns})


def incidents_query(
    statuses: set[IncidentStatus] | None, incident_id: uuid.UUID | None = None
) -> Select:
    taker, opening, call = aliased(User), aliased(Call), aliased(Call)
    # Answered on any of its calls: the opening red, or a later red added to it (05 §1).
    handover_answered = (
        select(call.id)
        .where(
            call.senior_id == Incident.senior_id,
            call.handover_answered.is_(True),
            call.created_at >= func.coalesce(opening.created_at, Incident.opened_at),
            or_(
                Incident.resolved_at.is_(None), call.created_at <= Incident.resolved_at
            ),
        )
        .exists()
    )
    query = (
        select(
            Incident.id,
            Senior.full_name.label("senior_full_name"),
            Senior.form_of_address.label("senior_form_of_address"),
            Incident.status,
            Incident.reason,
            Incident.opened_at,
            taker.display_name.label("taken_by_name"),
            Incident.taken_at,
            handover_answered.label("handover_answered"),
        )
        .join(Senior, Senior.id == Incident.senior_id)
        .outerjoin(taker, taker.id == Incident.taken_by)
        .outerjoin(opening, opening.id == Incident.opened_by_call_id)
        .order_by(Incident.opened_at.desc())
    )
    if statuses is not None:
        query = query.where(Incident.status.in_(statuses))
    if incident_id is not None:
        query = query.where(Incident.id == incident_id)
    return query


async def incident_summary(
    session: AsyncSession, incident_id: uuid.UUID
) -> IncidentSummary:
    row = (await session.execute(incidents_query(None, incident_id))).mappings().one()
    return IncidentSummary.model_validate(dict(row))


async def current_incident(session: AsyncSession, incident_id: uuid.UUID) -> Incident:
    incident = await session.get(Incident, incident_id, populate_existing=True)
    if incident is None:
        raise refuse(404, "not_found")
    return incident


# Resolved incidents are kept (05 §5); the list shows only the last day's (04 §1).
RESOLVED_SHOWN = timedelta(hours=24)


async def shown_incidents(
    statuses: set[IncidentStatus] | None,
) -> list[IncidentSummary]:
    """GET /incidents: every unresolved one, and those resolved in the last day."""
    query = incidents_query(statuses).where(
        or_(
            Incident.resolved_at.is_(None),
            Incident.resolved_at > func.now() - RESOLVED_SHOWN,
        )
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(query)).mappings().all()
    return [IncidentSummary.model_validate(dict(row)) for row in rows]


async def take(
    session: AsyncSession, incident_id: uuid.UUID, user_id: uuid.UUID
) -> IncidentSummary:
    """open -> in_progress for `user_id`, only where it is still open (05 §3); a
    refusal is raised as `take_refusal` names it (04 §2)."""
    taken = await session.execute(
        update(Incident)
        .where(Incident.id == incident_id, Incident.status == IncidentStatus.open)
        .values(
            status=IncidentStatus.in_progress,
            taken_by=user_id,
            taken_at=func.now(),
        )
        .returning(Incident.senior_id)
    )
    if (senior_id := taken.scalar()) is not None:
        note(session, Change(ChangeKind.incident_moved, senior_id, incident_id))
    else:
        incident = await current_incident(session, incident_id)
        reason = take_refusal(incident.status, incident.taken_by, user_id)
        if reason is not None:
            log.info("refused %s: user %s, incident %s", reason, user_id, incident_id)
            if reason != "already_done":
                raise refuse(409, reason)
            # Only someone else having it names who (04 §2).
            taker = incident.taken_by and await session.get(User, incident.taken_by)
            raise refuse(
                409, reason, taken_by_name=taker.display_name if taker else None
            )
    await session.commit()
    return await incident_summary(session, incident_id)


async def take_for_handover(
    session: AsyncSession, senior_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Answering the hand-over takes the senior's open incident for the on-duty
    employee (G16, UC-07 step 5); False when none is open, as when someone took it from
    the dashboard first. Never refuses: the call is already connecting. Doesn't commit.
    """
    taken = await session.execute(
        update(Incident)
        .where(Incident.senior_id == senior_id, Incident.status == IncidentStatus.open)
        .values(
            status=IncidentStatus.in_progress, taken_by=user_id, taken_at=func.now()
        )
        .returning(Incident.id)
    )
    if (incident_id := taken.scalar()) is None:
        return False
    note(session, Change(ChangeKind.incident_moved, senior_id, incident_id))
    return True


async def resolve(
    session: AsyncSession,
    incident_id: uuid.UUID,
    user_id: uuid.UUID,
    form: ResolutionForm,
) -> IncidentSummary:
    """in_progress -> resolved by `user_id`, only where it is still in progress; a
    refusal is raised as `resolve_refusal` names it (04 §2)."""
    resolved = await session.execute(
        update(Incident)
        .where(
            Incident.id == incident_id,
            Incident.status == IncidentStatus.in_progress,
        )
        .values(
            status=IncidentStatus.resolved,
            resolved_by=user_id,
            resolved_at=func.now(),
            outcome=form.outcome,
            note=form.note,
        )
        .returning(Incident.senior_id)
    )
    if (senior_id := resolved.scalar()) is not None:
        note(session, Change(ChangeKind.incident_moved, senior_id, incident_id))
    else:
        incident = await current_incident(session, incident_id)
        reason = resolve_refusal(
            incident.status,
            (incident.resolved_by, incident.outcome, incident.note),
            (user_id, form.outcome.name, form.note),
        )
        if reason is not None:
            log.info("refused %s: user %s, incident %s", reason, user_id, incident_id)
            raise refuse(409, reason)
    await session.commit()
    return await incident_summary(session, incident_id)
