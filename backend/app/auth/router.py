import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.schemas import (
    GrantView,
    OnDutyForm,
    ProfileView,
    StaffEditForm,
    StaffGrantForm,
    StaffListingView,
    StaffMemberView,
)
from app.auth.service import (
    Caller,
    current_caller,
    drop_push_token,
    edit_staff,
    grant_staff,
    refuse,
    require_roles,
    revoke_staff,
    save_push_token,
    set_on_duty,
    staff_listings,
)
from app.campaigns.service import warning_active
from app.core.db import get_session
from app.seniors.service import forms_of_address

router = APIRouter()


@router.get("/profile")
async def profile(
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProfileView:
    names = await forms_of_address(
        session, {g.senior_id for g in caller.grants if g.senior_id is not None}
    )
    return ProfileView(
        display_name=caller.user.display_name,
        phone_e164=caller.user.phone_e164,
        grants=[
            GrantView(
                role=g.role,
                senior_id=g.senior_id,
                senior_form_of_address=names.get(g.senior_id),
                relation=g.relation,
            )
            for g in caller.grants
        ],
        warning_active=await warning_active(session),
    )


# A longer token would overflow push_tokens.token, a String(512).
Token = Annotated[str, Path(max_length=512)]


@router.put("/profile/push-tokens/{token}", status_code=204)
async def put_push_token(
    token: Token,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Stores this device's push token; a shared device's token moves to its latest
    user (G4, Q19)."""
    await save_push_token(session, caller, token)


@router.delete("/profile/push-tokens/{token}", status_code=204)
async def delete_push_token(
    token: Token,
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Forgets the caller's own token, 204 whether or not it was there (G4, Q19)."""
    await drop_push_token(session, caller, token)


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
