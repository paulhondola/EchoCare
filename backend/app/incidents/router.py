import logging
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth.models import Role, User
from app.auth.service import Caller, refuse, require_roles
from app.core.db import engine, get_session
from app.incidents.models import Incident, IncidentStatus
from app.incidents.schemas import IncidentDetail, IncidentSummary, ResolutionForm
from app.incidents.service import resolve_refusal, take_refusal
from app.incidents.views import load_incident
from app.seniors.models import Senior
from app.voice.models import Call

log = logging.getLogger("sentinela.incidents")

router = APIRouter()


def parse_statuses(status: str | None) -> set[IncidentStatus] | None:
    """The comma-separated `status` filter, e.g. open,in_progress (04 §1); None for any."""
    if not status:
        return None
    try:
        return {IncidentStatus(s.strip()) for s in status.split(",") if s.strip()}
    except ValueError:
        raise refuse(422, "unknown_status") from None


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


# Resolved incidents are kept (05 §5); the list shows only the last day's (04 §1).
RESOLVED_SHOWN = timedelta(hours=24)


@router.get("/incidents")
async def list_incidents(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    status: str | None = None,
) -> list[IncidentSummary]:
    query = incidents_query(parse_statuses(status)).where(
        or_(
            Incident.resolved_at.is_(None),
            Incident.resolved_at > func.now() - RESOLVED_SHOWN,
        )
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(query)).mappings().all()
    return [IncidentSummary.model_validate(dict(row)) for row in rows]


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: uuid.UUID,
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentDetail:
    """One incident with the senior's address, caregivers, event and calls (04 §1)."""
    detail = await load_incident(session, incident_id)
    if detail is None:
        raise refuse(404, "not_found")
    return detail


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


@router.post("/incidents/{incident_id}/take")
async def take_incident(
    incident_id: uuid.UUID,
    caller: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentSummary:
    """Preiau: open -> in_progress, with who and when; nothing else changes (04 §2).

    Only where the incident is still open, so of two takers at once one wins (05 §3).
    """
    taken = await session.execute(
        update(Incident)
        .where(Incident.id == incident_id, Incident.status == IncidentStatus.open)
        .values(
            status=IncidentStatus.in_progress,
            taken_by=caller.user.id,
            taken_at=func.now(),
        )
        .returning(Incident.id)
    )
    if taken.first() is None:
        incident = await current_incident(session, incident_id)
        reason = take_refusal(incident.status, incident.taken_by, caller.user.id)
        if reason is not None:
            log.info(
                "refused %s: user %s, incident %s", reason, caller.user.id, incident_id
            )
            if reason != "already_done":
                raise refuse(409, reason)
            # Only someone else having it names who (04 §2).
            taker = incident.taken_by and await session.get(User, incident.taken_by)
            raise refuse(
                409, reason, taken_by_name=taker.display_name if taker else None
            )
    await session.commit()
    return await incident_summary(session, incident_id)


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: uuid.UUID,
    body: ResolutionForm,
    caller: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentSummary:
    """in_progress -> resolved with an outcome and a note. The code is unchanged and
    the senior returns to campaigns (04 §2, 03 §8)."""
    resolved = await session.execute(
        update(Incident)
        .where(
            Incident.id == incident_id,
            Incident.status == IncidentStatus.in_progress,
        )
        .values(
            status=IncidentStatus.resolved,
            resolved_by=caller.user.id,
            resolved_at=func.now(),
            outcome=body.outcome,
            note=body.note,
        )
        .returning(Incident.id)
    )
    if resolved.first() is None:
        incident = await current_incident(session, incident_id)
        reason = resolve_refusal(
            incident.status,
            (incident.resolved_by, incident.outcome, incident.note),
            (caller.user.id, body.outcome.name, body.note),
        )
        if reason is not None:
            log.info(
                "refused %s: user %s, incident %s", reason, caller.user.id, incident_id
            )
            raise refuse(409, reason)
    await session.commit()
    return await incident_summary(session, incident_id)
