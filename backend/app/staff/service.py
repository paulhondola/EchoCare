"""Granting staff roles (UC-14, auth-layer §3.4), for POST /staff and grant_das.py.

`user_for` also makes the user rows behind senior and caregiver grants (UC-01).
"""

import logging
import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import ROLE_ORDER, Grant, Role, User
from app.auth.service import refuse
from app.staff.schemas import StaffEditForm, StaffListingView

log = logging.getLogger("echocare.staff")

STAFF_ROLES = (Role.das, Role.medic)

# One lock for the writes that count or clear across all DAS rows: it serializes the
# last-das check (Q6) and the one-on-duty switch (P10), whose race on the partial unique
# index on on_duty would otherwise be a 500.
STAFF_LOCK = 20261016


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


async def staff_listings(
    session: AsyncSession, user_id: uuid.UUID | None = None
) -> list[StaffListingView]:
    """DAS employees and medics, by name, once per person (UC-14); one person if `user_id`."""
    query = (
        select(User, Grant.role)
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.role.in_(STAFF_ROLES))
        .order_by(User.display_name, User.phone_e164)
    )
    if user_id is not None:
        query = query.where(User.id == user_id)
    staff: dict[uuid.UUID, StaffListingView] = {}
    for user, role in await session.execute(query):
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


async def edit_staff(
    session: AsyncSession, user_id: uuid.UUID, form: StaffEditForm
) -> StaffListingView:
    """Sets the name and practice the form carries on a staff member (04 §2).

    Only people with a das or medic grant, and a practice only for a medic.
    """
    roles = (
        await session.scalars(
            select(Grant.role).where(
                Grant.user_id == user_id, Grant.role.in_(STAFF_ROLES)
            )
        )
    ).all()
    if not roles:
        log.info("refused not_found: staff %s", user_id)
        raise refuse(404, "not_found")
    if form.practice is not None and Role.medic not in roles:
        log.info("refused not_medic: staff %s", user_id)
        raise refuse(422, "not_medic")
    user = await session.get(User, user_id)
    for field, value in form.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    await session.commit()
    return (await staff_listings(session, user_id))[0]


async def revoke_staff(session: AsyncSession, user_id: uuid.UUID, role: Role) -> None:
    """Deletes the grant; no such grant is fine. The last `das` stays (409 wrong_state).

    Removing `das` also takes the person off duty. Incidents they hold stay theirs.
    """
    await session.execute(select(func.pg_advisory_xact_lock(STAFF_LOCK)))
    if role == Role.das:
        holders = (
            await session.scalars(select(Grant.user_id).where(Grant.role == Role.das))
        ).all()
        if holders == [user_id]:
            log.info("refused wrong_state: last das %s", user_id)
            await session.rollback()
            raise refuse(409, "wrong_state")
        await session.execute(
            update(User).where(User.id == user_id).values(on_duty=False)
        )
    await session.execute(
        delete(Grant).where(Grant.user_id == user_id, Grant.role == role)
    )
    await session.commit()


async def set_on_duty(session: AsyncSession, user_id: uuid.UUID | None) -> None:
    """Puts one DAS employee on duty and everyone else off; None puts nobody on duty."""
    await session.execute(select(func.pg_advisory_xact_lock(STAFF_LOCK)))
    if user_id is not None and not await session.scalar(
        select(Grant.id).where(Grant.user_id == user_id, Grant.role == Role.das)
    ):
        log.info("refused not_allowed: on duty %s holds no das grant", user_id)
        await session.rollback()
        raise refuse(403, "not_allowed")
    await session.execute(update(User).where(User.on_duty).values(on_duty=False))
    if user_id is not None:
        await session.execute(
            update(User).where(User.id == user_id).values(on_duty=True)
        )
    await session.commit()
