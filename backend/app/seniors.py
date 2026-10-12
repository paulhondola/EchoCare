"""Seniors, their caregivers and enrollment (UC-01, UC-04 step 1): the reads and
commands of seniors §3.3 and §3.4 (docs/specs/seniors-and-enrollment.md).

Fields are only ever added (ADR-001 §2.3). The code, calls, consent, watch and home
node join these reads with their own features.
"""

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, BeforeValidator, StringConstraints, field_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller, current_caller, refuse, require_roles
from app.db import get_session
from app.grants import user_for_number
from app.models import EnrollmentState, Grant, Role, Senior, User
from app.phones import is_mobile, normalize
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


# What a submit needs beyond the draft's own required fields (seniors SE4).
REQUIRED_TO_SUBMIT = ("street", "street_number")
# users.display_name is shorter than seniors.full_name (05 §1).
USER_NAME_LENGTH = 120


def blank_to_none(value: Any) -> Any:
    """An optional field left empty in a form is no value, not an empty string."""
    if isinstance(value, str):
        return value.strip() or None
    return value


def required(max_length: int) -> Any:
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length),
    ]


def optional(max_length: int) -> Any:
    # The limit sits on the text, not on the whole field: a constraint on `str | None`
    # is also applied to the None a blank becomes, and fails.
    text = Annotated[str, StringConstraints(max_length=max_length)]
    return Annotated[text | None, BeforeValidator(blank_to_none)]


class SeniorBody(BaseModel):
    """The registration, for POST and PUT /seniors (seniors §3.5). PUT replaces every
    field, so one left out becomes null."""

    full_name: required(200)
    form_of_address: required(120)
    phone: str
    street: optional(200) = None
    street_number: optional(20) = None
    block: optional(20) = None
    staircase: optional(20) = None
    floor: optional(20) = None
    apartment: optional(20) = None
    intercom_code: optional(40) = None
    key_holder: optional(200) = None
    landmark: optional(200) = None
    call_window: optional(60) = None

    @field_validator("phone")
    @classmethod
    def e164(cls, raw: str) -> str:
        # A landline is fine: the senior is called, and need not sign in.
        return normalize(raw)


def refused(
    status: int, reason: str, caller: Caller, senior_id: uuid.UUID, **extra: Any
) -> HTTPException:
    """A refusal about one senior, logged with the user id (auth-layer AL15). The
    request's transaction is rolled back when its session closes, so a refused
    command changes nothing."""
    log.info("refused %s: user %s, senior %s", reason, caller.user.id, senior_id)
    return refuse(status, reason, **extra)


def registration(body: SeniorBody) -> dict[str, Any]:
    """The body as seniors columns. Landline or not is worked out from the number."""
    return {
        **body.model_dump(exclude={"phone"}),
        "phone_e164": body.phone,
        "phone_is_landline": not is_mobile(body.phone),
    }


async def follow_number(session: AsyncSession, senior: Senior, caller: Caller) -> None:
    """The senior's grant follows the senior's number (seniors SE10, SE11).

    Called when the number is new or has changed: drops this senior's grant, then
    makes one for a mobile. A landline signs nobody in.
    """
    await session.execute(
        delete(Grant).where(Grant.role == Role.senior, Grant.senior_id == senior.id)
    )
    if senior.phone_is_landline:
        return
    user = await user_for_number(
        session, senior.phone_e164, senior.full_name[:USER_NAME_LENGTH]
    )
    # ON CONFLICT with no target: the at-most-one-senior-grant-per-user index stops
    # a number that already signs in as another senior, even of two saves at once.
    granted = await session.scalar(
        insert(Grant)
        .values(
            user_id=user.id,
            role=Role.senior,
            senior_id=senior.id,
            granted_by=caller.user.id,
        )
        .on_conflict_do_nothing()
        .returning(Grant.id)
    )
    if granted is None:
        raise refused(409, "phone_taken", caller, senior.id)


@router.post("/seniors", status_code=201)
async def create_senior(body: SeniorBody, caller: AsMedic, session: Db) -> SeniorPage:
    """A new senior in draft, registered by the caller (UC-01). Not repeat-safe: two
    posts make two drafts (seniors SE14)."""
    senior = Senior(medic_id=caller.user.id, **registration(body))
    session.add(senior)
    await session.flush()  # the database makes the id
    await follow_number(session, senior, caller)
    await session.commit()
    return await page(session, senior)


@router.put("/seniors/{senior_id}")
async def update_senior(
    senior_id: uuid.UUID, body: SeniorBody, caller: AsMedicOrDas, session: Db
) -> SeniorPage:
    """Replaces the registration, in any state (seniors SE9)."""
    # Locked, so a submit at the same moment sees either the old row or the new one.
    senior = await reachable_senior(
        session, caller, senior_id, Role.medic, Role.das, lock=True
    )
    if senior.enrollment_state != EnrollmentState.draft:
        missing = [name for name in REQUIRED_TO_SUBMIT if getattr(body, name) is None]
        if missing:
            raise refused(422, "missing_fields", caller, senior_id, fields=missing)
    number_changed = body.phone != senior.phone_e164
    for name, value in registration(body).items():
        setattr(senior, name, value)
    if number_changed:
        await session.flush()
        await follow_number(session, senior, caller)
    await session.commit()
    return await page(session, senior)
