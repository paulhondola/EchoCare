import logging
import uuid
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    StringConstraints,
    field_validator,
)
from sqlalchemy import ColumnElement, Select, delete, false, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Grant, Role, User
from app.auth.service import Caller, refuse
from app.core.phones import is_mobile, normalize
from app.seniors.models import EnrollmentState, Senior
from app.staff.service import user_for

log = logging.getLogger("sentinela.seniors")


class SeniorDetail(BaseModel):
    """Registration, address and access details (G13)."""

    id: uuid.UUID
    full_name: str
    form_of_address: str
    phone_e164: str
    phone_is_landline: bool
    street: str | None
    street_number: str | None
    block: str | None
    staircase: str | None
    floor: str | None
    apartment: str | None
    intercom_code: str | None
    key_holder: str | None
    landmark: str | None


class Caregiver(BaseModel):
    display_name: str
    phone_e164: str
    relation: str | None


def no_nul(value: str) -> str:
    # Postgres text cannot hold a NUL. Refuse it here, as a 422, not there, as a 500.
    if "\x00" in value:
        raise ValueError("the text contains a NUL character")
    return value


def text(max_length: int, min_length: int = 0) -> Any:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
        AfterValidator(no_nul),
    ]


# Enrollment states read back as their names; an unknown one as the bare string.
State = Annotated[str, BeforeValidator(lambda v: getattr(v, "value", v))]

# The registration form's optional fields (UC-01 steps 1 and 2); empty means none.
OPTIONAL = (
    "call_window",
    "street",
    "street_number",
    "block",
    "staircase",
    "floor",
    "apartment",
    "intercom_code",
    "key_holder",
    "landmark",
)


class SeniorForm(BaseModel):
    """POST /seniors and PUT /seniors/{id}'s body: the whole registration (UC-01)."""

    full_name: text(200, 1)
    form_of_address: text(120, 1)  # "doamna Maria"
    phone: str  # a landline or a mobile; which is worked out from the number
    call_window: text(60) | None = None
    street: text(200) | None = None
    street_number: text(20) | None = None
    block: text(20) | None = None
    staircase: text(20) | None = None
    floor: text(20) | None = None
    apartment: text(20) | None = None
    intercom_code: text(40) | None = None
    key_holder: text(200) | None = None
    landmark: text(200) | None = None

    @field_validator("phone")
    @classmethod
    def e164(cls, raw: str) -> str:
        return normalize(raw)

    @field_validator(*OPTIONAL)
    @classmethod
    def empty_is_none(cls, value: str | None) -> str | None:
        # A form's empty field stores nothing, not "".
        return value or None

    def columns(self) -> dict[str, Any]:
        return {
            **self.model_dump(exclude={"phone"}),
            "phone_e164": self.phone,
            "phone_is_landline": not is_mobile(self.phone),
        }


class CaregiverForm(BaseModel):
    """POST /seniors/{id}/caregivers's body (UC-01 step 3)."""

    display_name: text(120, 1)
    relation: text(60, 1)  # "fiica"
    phone: str

    @field_validator("phone")
    @classmethod
    def mobile_e164(cls, raw: str) -> str:
        e164 = normalize(raw)
        if not is_mobile(e164):
            raise ValueError("caregivers sign in by SMS: the number must be a mobile")
        return e164


class SeniorSummary(BaseModel):
    """One row of GET /seniors (04 §1), with the fields that exist today."""

    id: uuid.UUID
    full_name: str
    form_of_address: str
    # The number and whether it is a landline, for the apps' senior cards (seniors §3.3).
    phone_e164: str
    phone_is_landline: bool
    enrollment_state: State


class CaregiverView(Caregiver):
    user_id: uuid.UUID  # for DELETE /seniors/{id}/caregivers/{userId}


class MedicView(BaseModel):
    """The medic who registered the senior, on the senior's page (seniors §3.3)."""

    display_name: str
    practice: str | None


class SeniorView(SeniorDetail):
    """GET /seniors/{id} (04 §1): registration, address, medic and caregivers. One
    shape for every role (seniors SE7)."""

    call_window: str | None
    enrollment_state: State
    medic: MedicView
    caregivers: list[CaregiverView]


def reach(caller: Caller, role: Role | None = None) -> ColumnElement[bool]:
    """The seniors this caller reaches, as a condition on `seniors` (auth-layer §3.6).

    A medic their own seniors while they hold the grant, caregivers and the senior
    through grants naming them, DAS every senior past `draft`. The union, as AL2 says.

    `role` narrows it to what that one role reaches, for a home that shows one role
    (seniors SE6). It grants nothing: a role the caller does not hold reaches nobody.
    """
    held = caller.roles if role is None else caller.roles & {role}
    reaches = []
    if Role.medic in held:
        reaches.append(Senior.medic_id == caller.user.id)
    granted = [
        g.senior_id for g in caller.grants if g.role in held and g.senior_id is not None
    ]
    if granted:
        reaches.append(Senior.id.in_(granted))
    if Role.das in held:
        reaches.append(Senior.enrollment_state != EnrollmentState.draft)
    return or_(*reaches) if reaches else false()


def seniors_query(caller: Caller, role: Role | None = None) -> Select:
    return (
        select(Senior).where(reach(caller, role)).order_by(Senior.full_name, Senior.id)
    )


async def reach_senior(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID, *, lock: bool = False
) -> Senior:
    """The senior, if the caller reaches them; otherwise 404 `not_found` (AL8).

    `lock` is FOR NO KEY UPDATE, not FOR UPDATE: inserting a grant, a call or an
    incident takes FOR KEY SHARE on the senior's row through its foreign key, which a
    plain FOR UPDATE would block (seniors §6.2).
    """
    query = select(Senior).where(Senior.id == senior_id, reach(caller))
    if lock:
        query = query.with_for_update(key_share=True)
    senior = await session.scalar(query)
    if senior is None:
        log.info("refused not_found: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(404, "not_found")
    return senior


async def own_senior(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> Senior:
    """A senior the caller registered, for the medic's commands (04 §2).

    Out of reach is 404; within reach but someone else's, such as DAS looking at a
    submitted senior, is 403 `not_allowed`. The row stays locked until the request
    ends, so the medic's commands on one senior run one at a time: submit's check
    cannot interleave with an edit or a caregiver's removal.
    """
    senior = await reach_senior(session, caller, senior_id, lock=True)
    if Role.medic not in caller.roles or senior.medic_id != caller.user.id:
        log.info("refused not_allowed: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(403, "not_allowed")
    return senior


async def sync_senior_grant(session: AsyncSession, senior: Senior) -> None:
    """A mobile number is the senior's own grant; a landline has none (UC-01 step 3).

    A changed number drops the old number's grant. When the number already holds a
    senior grant, for a couple sharing one mobile, the second senior gets none and
    still receives every call (AL7).
    """
    await session.execute(
        delete(Grant).where(
            Grant.senior_id == senior.id,
            Grant.role == Role.senior,
            Grant.user_id.not_in(
                select(User.id).where(User.phone_e164 == senior.phone_e164)
            ),
        )
    )
    if senior.phone_is_landline:
        return
    user = await user_for(session, senior.phone_e164, senior.full_name[:120])
    # No conflict target: covers both the per-senior key and the AL7 index.
    await session.execute(
        insert(Grant)
        .values(
            user_id=user.id,
            role=Role.senior,
            senior_id=senior.id,
            granted_by=senior.medic_id,
        )
        .on_conflict_do_nothing()
    )


def caregivers_query(senior_id: uuid.UUID) -> Select:
    return (
        select(
            User.id.label("user_id"),
            User.display_name,
            User.phone_e164,
            Grant.relation,
        )
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.senior_id == senior_id, Grant.role == Role.caregiver)
        .order_by(User.display_name, User.id)
    )


async def senior_view(session: AsyncSession, senior: Senior) -> SeniorView:
    medic = await session.get(User, senior.medic_id)
    caregivers = (await session.execute(caregivers_query(senior.id))).mappings()
    fields = SeniorView.model_fields.keys() - {"medic", "caregivers"}
    return SeniorView(
        **{name: getattr(senior, name) for name in fields},
        medic=MedicView.model_validate(medic, from_attributes=True),
        caregivers=[CaregiverView.model_validate(dict(c)) for c in caregivers],
    )


async def forms_of_address(
    session: AsyncSession, senior_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """For GET /me's grants (auth-layer §3.3)."""
    if not senior_ids:
        return {}
    rows = await session.execute(
        select(Senior.id, Senior.form_of_address).where(Senior.id.in_(senior_ids))
    )
    return dict(rows.tuples().all())


REQUIRED_TO_SUBMIT = ("street", "street_number")


def missing_address(registration: Senior | SeniorForm) -> list[str]:
    return [name for name in REQUIRED_TO_SUBMIT if not getattr(registration, name)]


async def has_caregiver(session: AsyncSession, senior_id: uuid.UUID) -> bool:
    return await session.scalar(
        select(
            select(Grant.id)
            .where(Grant.senior_id == senior_id, Grant.role == Role.caregiver)
            .exists()
        )
    )


async def missing_to_submit(session: AsyncSession, senior: Senior) -> list[str]:
    missing = missing_address(senior)
    if not await has_caregiver(session, senior.id):
        missing.append("caregiver")
    return missing


async def move(
    session: AsyncSession,
    caller: Caller,
    senior: Senior,
    before: EnrollmentState,
    after: EnrollmentState,
) -> None:
    """`before` -> `after`, only where the senior is still `before`, so of two at once
    one wins (05 §3's pattern). Already `after` is `already_done`, anything else
    `wrong_state`; either way nothing changes (04 §0)."""
    moved = await session.scalar(
        update(Senior)
        .where(Senior.id == senior.id, Senior.enrollment_state == before)
        .values(enrollment_state=after)
        .returning(Senior.id)
    )
    if moved is None:
        await session.refresh(senior, ["enrollment_state"])
        reason = "already_done" if senior.enrollment_state == after else "wrong_state"
        log.info("refused %s: user %s, senior %s", reason, caller.user.id, senior.id)
        raise refuse(409, reason)
    await session.commit()
    await session.refresh(senior, ["enrollment_state"])


def enrollments_query() -> Select:
    """GET /enrollments: waiting for DAS, oldest registration first (04 §1)."""
    return (
        select(Senior)
        .where(Senior.enrollment_state == EnrollmentState.submitted)
        .order_by(Senior.created_at, Senior.id)
    )
