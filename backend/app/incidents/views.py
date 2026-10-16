import uuid
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth.models import Grant, Role, User
from app.incidents.models import Event, Incident
from app.incidents.schemas import (
    CallDetail,
    IncidentDetail,
    ReportView,
    TriggerEventView,
    TurnView,
)
from app.seniors.models import Senior
from app.seniors.schemas import CaregiverSummary, SeniorDetail
from app.voice.models import Call, CallTurn, StatusReport


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


def caregivers_query(senior_id: uuid.UUID) -> Select:
    return (
        select(User.display_name, User.phone_e164, Grant.relation)
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.senior_id == senior_id, Grant.role == Role.caregiver)
        .order_by(User.display_name)
    )


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
    )


def call_detail(
    call: Call, reports: list[ReportView], turns: list[TurnView]
) -> CallDetail:
    columns = CallDetail.model_fields.keys() - {"reports", "turns"}
    fields = {name: getattr(call, name) for name in columns}
    return CallDetail.model_validate({**fields, "reports": reports, "turns": turns})
