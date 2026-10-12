"""Granting staff roles (UC-14, auth-layer §3.4), for POST /staff and grant_das.py.

`user_for` also makes the user rows behind senior and caregiver grants (UC-01)."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Grant, Role, User


async def user_for(session: AsyncSession, phone_e164: str, display_name: str) -> User:
    """The number's user row, made with `display_name` if it has none (05 §4).

    ON CONFLICT DO NOTHING, so two grants at once make one row and an existing user
    keeps their name.
    """
    await session.execute(
        insert(User)
        .values(phone_e164=phone_e164, display_name=display_name)
        .on_conflict_do_nothing(index_elements=[User.phone_e164])
    )
    return await session.scalar(select(User).where(User.phone_e164 == phone_e164))


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
    user = await user_for(session, phone_e164, display_name)
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
