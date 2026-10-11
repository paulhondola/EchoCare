import logging
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, StringConstraints, field_validator, model_validator
from sqlalchemy import Select, false, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth import Caller, current_caller, refuse, require_roles
from app.db import engine, get_session
from app.incidents import IncidentStatus, resolve_refusal, take_refusal
from app.models import Call, Incident, IncidentOutcome, Role, Senior, User
from app.phones import is_mobile, normalize
from app.settings import check_environment, get_settings
from app.staff import grant_staff

# Our own loggers at INFO, for refusals (auth-layer AL15); uvicorn sets up only its own.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("sentinela").setLevel(logging.INFO)
log = logging.getLogger("sentinela.incidents")

settings = get_settings()
check_environment(settings)

# Everything under /api, docs included, so the API and the dashboard can share one domain.
app = FastAPI(
    title="Sentinela",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
# Browser requests only from the dashboard's own address (01 §4, channel 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api")


@api.get("/health")
async def health() -> dict[str, str]:
    # Fails when the database is unreachable, so Railway holds back a broken deploy (06 §1).
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "env": settings.app_env}


class GrantView(BaseModel):
    role: str
    senior_id: uuid.UUID | None


class Me(BaseModel):
    """GET /me (auth-layer §3.3). Fields are only ever added: old apps read new servers."""

    display_name: str
    phone_e164: str
    grants: list[GrantView]


@api.get("/me")
async def me(caller: Annotated[Caller, Depends(current_caller)]) -> Me:
    return Me(
        display_name=caller.user.display_name,
        phone_e164=caller.user.phone_e164,
        grants=[GrantView(role=g.role, senior_id=g.senior_id) for g in caller.grants],
    )


Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
Practice = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class StaffGrant(BaseModel):
    """POST /staff's body (auth-layer §3.4)."""

    display_name: Name
    phone: str
    role: Literal["das", "medic"]
    practice: Practice | None = None

    @model_validator(mode="before")
    @classmethod
    def practice_only_for_medics(cls, data: Any) -> Any:
        # Ignored for das (§3.4), so a form's empty practice field refuses nothing.
        if isinstance(data, dict) and data.get("role") != "medic":
            return {**data, "practice": None}
        return data

    @field_validator("phone")
    @classmethod
    def mobile_e164(cls, raw: str) -> str:
        e164 = normalize(raw)
        if not is_mobile(e164):
            raise ValueError("staff sign in by SMS: the number must be a mobile")
        return e164

    @model_validator(mode="after")
    def medic_has_practice(self) -> Self:
        if self.role == "medic" and self.practice is None:
            raise ValueError("a medic needs a practice")
        return self


class StaffMember(BaseModel):
    display_name: str
    phone_e164: str
    role: str
    practice: str | None


@api.post("/staff", status_code=201)
async def grant_staff_member(
    body: StaffGrant,
    caller: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StaffMember:
    user = await grant_staff(
        session,
        body.display_name,
        body.phone,
        Role(body.role),
        body.practice,
        caller.user.id,
    )
    if user is None:
        raise refuse(409, "already_done")
    return StaffMember(
        display_name=user.display_name,
        phone_e164=user.phone_e164,
        role=body.role,
        practice=user.practice,
    )


# One row of GET /incidents (04 §1). Names follow the incidents and seniors tables (05 §1)
# and match the dashboard's Incident type (dashboard/src/api.ts).
class IncidentSummary(BaseModel):
    id: uuid.UUID
    senior_full_name: str
    senior_form_of_address: str
    status: IncidentStatus
    reason: str
    opened_at: datetime
    taken_by_name: str | None
    taken_at: datetime | None
    handover_answered: bool


def parse_statuses(status: str | None) -> set[IncidentStatus] | None:
    """The comma-separated `status` filter, e.g. open,in_progress (04 §1); None for any."""
    if not status:
        return None
    try:
        return {IncidentStatus(s.strip()) for s in status.split(",") if s.strip()}
    except ValueError:
        raise HTTPException(422, "unknown status") from None


def incidents_query(
    statuses: set[IncidentStatus] | None, incident_id: uuid.UUID | None = None
) -> Select:
    taker = aliased(User)
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
            # Set on the call that opened the incident when DAS picked up the hand-over.
            func.coalesce(Call.handover_answered, false()).label("handover_answered"),
        )
        .join(Senior, Senior.id == Incident.senior_id)
        .outerjoin(taker, taker.id == Incident.taken_by)
        .outerjoin(Call, Call.id == Incident.opened_by_call_id)
        .order_by(Incident.opened_at.desc())
    )
    if statuses is not None:
        query = query.where(Incident.status.in_(statuses))
    if incident_id is not None:
        query = query.where(Incident.id == incident_id)
    return query


@api.get("/incidents")
async def list_incidents(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    status: str | None = None,
) -> list[IncidentSummary]:
    query = incidents_query(parse_statuses(status))
    async with engine.connect() as conn:
        rows = (await conn.execute(query)).mappings().all()
    return [IncidentSummary.model_validate(dict(row)) for row in rows]


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


@api.post("/incidents/{incident_id}/take")
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
            taker = incident.taken_by and await session.get(User, incident.taken_by)
            raise refuse(
                409, reason, taken_by_name=taker.display_name if taker else None
            )
    await session.commit()
    return await incident_summary(session, incident_id)


Note = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]


class Resolution(BaseModel):
    """POST /incidents/{id}/resolve's body (04 §2)."""

    outcome: IncidentOutcome
    note: Note


@api.post("/incidents/{incident_id}/resolve")
async def resolve_incident(
    incident_id: uuid.UUID,
    body: Resolution,
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
            incident.resolved_by,
            incident.outcome,
            caller.user.id,
            body.outcome,
        )
        if reason is not None:
            log.info(
                "refused %s: user %s, incident %s", reason, caller.user.id, incident_id
            )
            raise refuse(409, reason)
    await session.commit()
    return await incident_summary(session, incident_id)


# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)
