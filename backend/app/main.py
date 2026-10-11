import logging
import uuid
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, StringConstraints, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller, current_caller, init_firebase, refuse, require_roles
from app.db import engine, get_session
from app.models import Role
from app.phones import is_mobile, normalize
from app.settings import check_environment, check_firebase, get_settings
from app.staff import grant_staff

# Our own loggers at INFO, for refusals (auth-layer AL15); uvicorn sets up only its own.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("sentinela").setLevel(logging.INFO)

settings = get_settings()
check_environment(settings)
check_firebase(settings)
init_firebase(settings.firebase_service_account)

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


# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)
