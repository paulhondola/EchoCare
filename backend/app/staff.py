"""Granting staff roles (UC-14, auth-layer §3.4), for POST /staff and grant_das.py."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Grant, Role, User


async def grant_staff(
    session: AsyncSession,
    display_name: str,
    phone_e164: str,
    role: Role,
    practice: str | None,
    granted_by: uuid.UUID | None,
) -> User | None:
    """Grants `role` to the number, making its user row if it has none.

    Returns the user, or None when the number already held the role; then nothing
    changed. An existing user keeps their name; a medic grant sets the practice. Both
    inserts are ON CONFLICT DO NOTHING, so two DAS granting at once cannot both win.
    """
    await session.execute(
        insert(User)
        .values(phone_e164=phone_e164, display_name=display_name)
        .on_conflict_do_nothing(index_elements=[User.phone_e164])
    )
    user = await session.scalar(select(User).where(User.phone_e164 == phone_e164))
    granted = await session.scalar(
        insert(Grant)
        .values(user_id=user.id, role=role, granted_by=granted_by)
        .on_conflict_do_nothing()
        .returning(Grant.id)
    )
    if granted is None:
        await session.rollback()
        return None
    if role == Role.medic:
        user.practice = practice
    await session.commit()
    return user
