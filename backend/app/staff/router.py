import uuid
from typing import Annotated, Any, Literal, Self

from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import ROLE_ORDER, Grant, Role, User
from app.auth.service import Caller, refuse, require_roles
from app.core.db import get_session
from app.core.phones import is_mobile, normalize
from app.staff.service import grant_staff

router = APIRouter()

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


@router.post("/staff", status_code=201)
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


class StaffListing(BaseModel):
    """One row of GET /staff (04 §1): a person with a das or medic grant, once."""

    id: uuid.UUID
    display_name: str
    phone_e164: str
    practice: str | None
    roles: list[str]  # das before medic, like /me's grants
    on_duty: bool


STAFF_ROLES = (Role.das, Role.medic)


@router.get("/staff")
async def list_staff(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[StaffListing]:
    """DAS employees and medics, by name, for the dashboard's 'Personal' (UC-14)."""
    rows = await session.execute(
        select(User, Grant.role)
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.role.in_(STAFF_ROLES))
        .order_by(User.display_name, User.phone_e164)
    )
    staff: dict[uuid.UUID, StaffListing] = {}
    for user, role in rows:
        listing = staff.setdefault(
            user.id,
            StaffListing(
                id=user.id,
                display_name=user.display_name,
                phone_e164=user.phone_e164,
                practice=user.practice,
                roles=[],
                on_duty=user.on_duty,
            ),
        )
        listing.roles.append(role)
    for listing in staff.values():
        listing.roles.sort(key=lambda r: ROLE_ORDER.index(Role(r)))
    return list(staff.values())
