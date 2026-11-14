import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, refuse, require_roles
from app.core.db import get_session
from app.homenode.service import room_for
from app.incidents.models import IncidentStatus
from app.incidents.schemas import (
    EventForm,
    EventView,
    IncidentDetail,
    IncidentSummary,
    ResolutionForm,
)
from app.incidents.service import (
    load_incident,
    record_event,
    resolve,
    shown_incidents,
    take,
)

router = APIRouter()


@router.post("/me/events")
async def send_event(
    body: EventForm,
    caller: Annotated[Caller, Depends(require_roles(Role.senior))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventView:
    """„Sunați-mă”: queues a yellow wellbeing call, or joins the one already there
    (UC-10, 04 §3)."""
    senior_id = next(g.senior_id for g in caller.grants if g.role == Role.senior)
    return await record_event(session, senior_id, body, datetime.now(UTC))


def parse_statuses(status: str | None) -> set[IncidentStatus] | None:
    """The comma-separated `status` filter, e.g. open,in_progress (04 §1); None for any."""
    if not status:
        return None
    try:
        return {IncidentStatus(s.strip()) for s in status.split(",") if s.strip()}
    except ValueError:
        raise refuse(422, "unknown_status") from None


@router.get("/incidents")
async def list_incidents(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    status: str | None = None,
) -> list[IncidentSummary]:
    return await shown_incidents(parse_statuses(status))


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
    # `incidents` can't import `homenode`, which sits above it (ADR-005)
    detail.room = await room_for(session, detail.senior.id)
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
    return await take(session, incident_id, caller.user.id)


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: uuid.UUID,
    body: ResolutionForm,
    caller: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IncidentSummary:
    """in_progress -> resolved with an outcome and a note. The code is unchanged and
    the senior returns to campaigns (04 §2, 03 §8)."""
    return await resolve(session, incident_id, caller.user.id, body)
