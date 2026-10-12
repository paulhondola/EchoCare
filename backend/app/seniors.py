"""Seniors, their caregivers and enrollment (UC-01, UC-04 step 1): the reads and
commands of seniors §3.3 and §3.4 (docs/specs/seniors-and-enrollment.md).

Fields are only ever added (ADR-001 §2.3). The code, calls, consent, watch and home
node join these reads with their own features.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller, current_caller, require_roles
from app.db import get_session
from app.models import Grant, Role, Senior, User
from app.reach import reachable_senior, reaches

log = logging.getLogger("sentinela.seniors")
router = APIRouter()

# Who may call, as route parameters. A caller without the role gets 403 not_allowed.
AnyCaller = Annotated[Caller, Depends(current_caller)]
AsMedic = Annotated[Caller, Depends(require_roles(Role.medic))]
AsDas = Annotated[Caller, Depends(require_roles(Role.das))]
# The registration and the caregivers may be changed by either (seniors SE9).
AsMedicOrDas = Annotated[Caller, Depends(require_roles(Role.medic, Role.das))]
Db = Annotated[AsyncSession, Depends(get_session)]


class SeniorRow(BaseModel):
    """One row of GET /seniors and GET /enrollments (seniors §3.3)."""

    id: uuid.UUID
    full_name: str
    form_of_address: str
    phone_e164: str
    phone_is_landline: bool
    # A string, not the enum: a state a newer copy added must still be served.
    enrollment_state: str


class MedicView(BaseModel):
    display_name: str
    practice: str | None


class CaregiverView(BaseModel):
    user_id: uuid.UUID
    display_name: str
    relation: str | None
    phone_e164: str


class SeniorPage(SeniorRow):
    """GET /seniors/{id}, and the answer of every senior command: one shape for every
    role (seniors SE7)."""

    street: str | None
    street_number: str | None
    block: str | None
    staircase: str | None
    floor: str | None
    apartment: str | None
    intercom_code: str | None
    key_holder: str | None
    landmark: str | None
    call_window: str | None
    medic: MedicView
    caregivers: list[CaregiverView]


SENIOR_COLUMNS = SeniorPage.model_fields.keys() - {"medic", "caregivers"}


async def page(session: AsyncSession, senior: Senior) -> SeniorPage:
    medic = await session.get(User, senior.medic_id)
    caregivers = await session.execute(
        select(
            User.id.label("user_id"), User.display_name, Grant.relation, User.phone_e164
        )
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.senior_id == senior.id, Grant.role == Role.caregiver)
        .order_by(User.display_name, User.id)
    )
    return SeniorPage.model_validate(
        {
            **{name: getattr(senior, name) for name in SENIOR_COLUMNS},
            "medic": MedicView.model_validate(medic, from_attributes=True),
            "caregivers": [dict(c) for c in caregivers.mappings()],
        }
    )


@router.get("/seniors")
async def list_seniors(
    caller: AnyCaller, session: Db, role: Role | None = None
) -> list[SeniorRow]:
    """The seniors the caller reaches, newest first. `role` narrows the list to one
    role's reach and grants nothing (seniors SE6)."""
    seniors = await session.scalars(
        select(Senior)
        .where(reaches(caller, *([role] if role else [])))
        .order_by(Senior.created_at.desc(), Senior.id.desc())
    )
    return [SeniorRow.model_validate(s, from_attributes=True) for s in seniors]


@router.get("/seniors/{senior_id}")
async def get_senior(
    senior_id: uuid.UUID, caller: AnyCaller, session: Db
) -> SeniorPage:
    return await page(session, await reachable_senior(session, caller, senior_id))
