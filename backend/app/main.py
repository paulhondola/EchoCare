import uuid
from datetime import datetime

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Select, false, func, select, text
from sqlalchemy.orm import aliased

from app.db import engine
from app.incidents import IncidentStatus
from app.models import Call, Incident, Senior, User
from app.settings import check_environment, get_settings

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


def incidents_query(statuses: set[IncidentStatus] | None) -> Select:
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
    return query


@api.get("/incidents")
async def list_incidents(status: str | None = None) -> list[IncidentSummary]:
    query = incidents_query(parse_statuses(status))
    async with engine.connect() as conn:
        rows = (await conn.execute(query)).mappings().all()
    return [IncidentSummary.model_validate(dict(row)) for row in rows]


# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)
