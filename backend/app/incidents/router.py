import logging
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role, User
from app.auth.service import Caller, refuse, require_roles
from app.core.db import engine, get_session
from app.incidents.models import Incident, IncidentStatus
from app.incidents.schemas import IncidentDetail, IncidentSummary, ResolutionForm
from app.incidents.service import (
    current_incident,
    incident_summary,
    incidents_query,
    load_incident,
    resolve_refusal,
    take_refusal,
)

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
