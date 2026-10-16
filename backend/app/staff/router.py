import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, refuse, require_roles
from app.core.db import get_session
from app.staff.schemas import (
    OnDutyForm,
    StaffEditForm,
    StaffGrantForm,
    StaffListingView,
    StaffMemberView,
)
from app.staff.service import (
    edit_staff,
    grant_staff,
    revoke_staff,
    set_on_duty,
    staff_listings,
)

router = APIRouter()


@router.post("/staff", status_code=201)
async def grant_staff_member(
    body: StaffGrantForm,
    caller: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StaffMemberView:
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
    return StaffMemberView(
        display_name=user.display_name,
        phone_e164=user.phone_e164,
        role=body.role,
        practice=user.practice,
    )


@router.get("/staff")
async def list_staff(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[StaffListingView]:
    """DAS employees and medics, by name, for the dashboard's 'Personal' (UC-14)."""
    return await staff_listings(session)


@router.patch("/staff/{user_id}")
async def edit_staff_member(
    user_id: uuid.UUID,
    body: StaffEditForm,
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StaffListingView:
    """Edits a staff member's name and practice (04 §2); the phone stays (Q8)."""
    return await edit_staff(session, user_id, body)


@router.delete("/staff/{user_id}/roles/{role}", status_code=204)
async def remove_staff_role(
    user_id: uuid.UUID,
    role: Literal["das", "medic"],
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Removes a staff role; the last das employee stays (04 §2, Q6)."""
    await revoke_staff(session, user_id, Role(role))


@router.put("/staff/on-duty", status_code=204)
async def put_on_duty(
    body: OnDutyForm,
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Marks one DAS employee on duty and clears all others (P10)."""
    await set_on_duty(session, body.user_id)


@router.delete("/staff/on-duty", status_code=204)
async def clear_on_duty(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Nobody on duty; the hand-over already handles that (04 §4.2)."""
    await set_on_duty(session, None)
