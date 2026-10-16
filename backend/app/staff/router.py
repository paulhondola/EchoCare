import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import ROLE_ORDER, Grant, Role, User
from app.auth.service import Caller, refuse, require_roles
from app.core.db import get_session
from app.staff.schemas import StaffGrantForm, StaffListingView, StaffMemberView
from app.staff.service import grant_staff

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


STAFF_ROLES = (Role.das, Role.medic)


@router.get("/staff")
async def list_staff(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[StaffListingView]:
    """DAS employees and medics, by name, for the dashboard's 'Personal' (UC-14)."""
    rows = await session.execute(
        select(User, Grant.role)
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.role.in_(STAFF_ROLES))
        .order_by(User.display_name, User.phone_e164)
    )
    staff: dict[uuid.UUID, StaffListingView] = {}
    for user, role in rows:
        listing = staff.setdefault(
            user.id,
            StaffListingView(
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
