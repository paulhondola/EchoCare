"""Who reaches which senior (auth-layer §3.6), as one SQL condition (seniors SE5).

Every list and every single lookup goes through `reaches`, so the two cannot disagree.
"""

import logging
import uuid

from sqlalchemy import ColumnElement, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller, refuse
from app.models import EnrollmentState, Role, Senior

log = logging.getLogger("sentinela.reach")


def reaches(caller: Caller, *roles: Role) -> ColumnElement[bool]:
    """True for the seniors `caller` reaches through `roles` (seniors §3.1).

    With no role named, every role the caller holds counts. A caller who holds none
    of the named roles reaches nothing.
    """
    held = caller.roles
    counted = held.intersection(roles) if roles else held
    clauses: list[ColumnElement[bool]] = []
    if Role.medic in counted:
        # Only while they hold the medic grant: revoking it cuts access even though
        # medic_id still points at them (auth-layer §3.6).
        clauses.append(Senior.medic_id == caller.user.id)
    for role in (Role.caregiver, Role.senior):
        if role in counted:
            named = [g.senior_id for g in caller.grants if g.role == role]
            clauses.append(Senior.id.in_(named))
    if Role.das in counted:
        # Submitted or later, written as "not draft" so that a state a newer copy
        # added still counts (ADR-001 §2.3).
        clauses.append(Senior.enrollment_state != EnrollmentState.draft)
    return or_(*clauses) if clauses else false()


async def reachable_senior(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    *roles: Role,
    lock: bool = False,
) -> Senior:
    """The senior, if `caller` reaches them through `roles`.

    Otherwise 404 not_found, the answer an id that does not exist gets (AL8).
    `lock` holds the row until the transaction ends, for a command that reads the
    state and then writes. It is FOR NO KEY UPDATE, not FOR UPDATE: a grant insert
    takes FOR KEY SHARE on the senior row through its foreign key, which a plain FOR
    UPDATE would block, and an add and a PUT that bring one new number would deadlock.
    """
    query = select(Senior).where(Senior.id == senior_id, reaches(caller, *roles))
    if lock:
        query = query.with_for_update(key_share=True)
    senior = await session.scalar(query)
    if senior is None:
        log.info("refused not_found: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(404, "not_found")
    return senior
