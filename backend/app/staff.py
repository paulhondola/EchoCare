"""Staff roles (UC-14): granting them, for POST /staff and grant_das.py (auth-layer
§3.4), and listing who holds them, for GET /staff (04 §1)."""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.grants import user_for_number
from app.models import ROLE_ORDER, Grant, Role, User

# The roles DAS grants (UC-14). GET /staff lists who holds them.
STAFF_ROLES = (Role.das, Role.medic)


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
    user = await user_for_number(session, phone_e164, display_name)
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


async def list_staff(session: AsyncSession) -> list[tuple[User, list[str]]]:
    """Everyone who holds a das or a medic grant, by name, each with those roles in
    GET /me's order (seniors §3.3)."""
    rows = await session.execute(
        select(User, Grant.role)
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.role.in_(STAFF_ROLES))
        .order_by(User.display_name, User.id)
    )
    staff: dict[uuid.UUID, tuple[User, list[str]]] = {}
    for user, role in rows:
        staff.setdefault(user.id, (user, []))[1].append(role)
    return [
        (user, sorted(roles, key=ROLE_ORDER.index)) for user, roles in staff.values()
    ]
