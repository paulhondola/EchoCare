"""Who is calling (01 §6): verify the Firebase token, then find the number's grants.

The refusals and their reasons are auth-layer §3.2; the steps are auth-layer §3.1.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated, Any

import firebase_admin
import google.auth.credentials
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import ROLE_ORDER, Grant, PushToken, Role, User
from app.auth.schemas import StaffEditForm, StaffListingView
from app.core.db import get_session
from app.core.phones import mask, normalize

log = logging.getLogger("echocare.auth")

# auto_error=False: a missing or non-Bearer header gets our own 401 body. It also
# gives Swagger its Authorize button.
bearer = HTTPBearer(auto_error=False)

# One Firebase project serves every environment (auth-layer AL13).
FIREBASE_PROJECT_ID = "echocare-app"


class _NoKey(credentials.Base):
    """No service account (auth-layer AL11). Verifying a token needs only the project id
    and Google's public keys, but the Admin SDK loads a credential before it verifies."""

    def get_credential(self) -> google.auth.credentials.Credentials:
        return google.auth.credentials.AnonymousCredentials()


_firebase = firebase_admin.initialize_app(_NoKey(), {"projectId": FIREBASE_PROJECT_ID})


def refuse(status: int, reason: str, **extra: Any) -> HTTPException:
    """A refusal in the shape every client parses: {"detail": {"reason": ...}}.

    `extra` adds fields next to the reason, such as who has an incident (04 §2).
    """
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return HTTPException(status, {"reason": reason, **extra}, headers=headers)


def verify_token(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict[str, Any]:
    """The token's claims (auth-layer §3.1 step 2).

    A plain def on purpose: firebase-admin blocks, so FastAPI runs this in its thread
    pool and live calls keep the event loop (01 §8).
    """
    if creds is None:
        log.info("refused not_signed_in: no bearer token")
        raise refuse(401, "not_signed_in")
    try:
        return auth.verify_id_token(creds.credentials, app=_firebase)
    except auth.CertificateFetchError:
        log.warning(
            "refused auth_unavailable: Google's public keys could not be fetched"
        )
        raise refuse(503, "auth_unavailable") from None
    except auth.InvalidIdTokenError, ValueError:
        # InvalidIdTokenError covers expired and wrongly signed tokens, ValueError one
        # that is not a token at all; neither class derives from the other.
        log.info("refused not_signed_in: invalid token")
        raise refuse(401, "not_signed_in") from None


@dataclass(frozen=True)
class Caller:
    """The signed-in user and every grant they hold, in GET /me's order (AL2)."""

    user: User
    grants: list[Grant]

    @property
    def roles(self) -> set[Role]:
        return {Role(g.role) for g in self.grants}


async def current_caller(
    claims: Annotated[dict[str, Any], Depends(verify_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Caller:
    """auth-layer §3.1 steps 3 to 5."""
    raw = claims.get("phone_number")
    if not raw:
        log.info("refused not_signed_in: token without phone_number")
        raise refuse(401, "not_signed_in")
    try:
        phone = normalize(raw)
    except ValueError:
        log.info("refused not_registered: %s", mask(raw))
        raise refuse(403, "not_registered") from None
    # One round trip: the user and their grants (auth-layer §3.1 step 4).
    rows = (
        await session.execute(
            select(User, Grant)
            .outerjoin(Grant, Grant.user_id == User.id)
            .where(User.phone_e164 == phone)
        )
    ).all()
    grants = sorted(
        (g for _, g in rows if g is not None),
        key=lambda g: (ROLE_ORDER.index(g.role), g.created_at, g.id),
    )
    if not grants:
        log.info(
            "refused not_registered: %s",
            f"user {rows[0][0].id}" if rows else mask(phone),
        )
        raise refuse(403, "not_registered")
    user = rows[0][0]
    if user.firebase_uid != claims["uid"]:
        if user.firebase_uid is not None:
            log.warning("firebase_uid changed for user %s", user.id)
        user.firebase_uid = claims["uid"]
        await session.commit()
    return Caller(user, grants)


async def save_push_token(session: AsyncSession, caller: Caller, token: str) -> None:
    """The token is the caller's now, even if another user held it: it belongs to
    whoever signed in on the device last (Q19)."""
    await session.execute(
        insert(PushToken)
        .values(user_id=caller.user.id, token=token)
        .on_conflict_do_update(
            index_elements=[PushToken.token],
            set_={"user_id": caller.user.id, "updated_at": func.now()},
        )
    )
    await session.commit()


async def drop_push_token(session: AsyncSession, caller: Caller, token: str) -> None:
    """Only the caller's own row; someone else's token, or none, is a no-op (Q19)."""
    await session.execute(
        delete(PushToken).where(
            PushToken.token == token, PushToken.user_id == caller.user.id
        )
    )
    await session.commit()


async def drop_dead_tokens(session: AsyncSession, tokens: list[str]) -> None:
    """Tokens Firebase says no longer reach a device (04 §6), whoever held them.
    Doesn't commit."""
    await session.execute(delete(PushToken).where(PushToken.token.in_(tokens)))


def require_roles(*roles: Role):
    """A dependency: the caller, if any of their grants has one of `roles` (AL2)."""

    async def caller_with_role(
        caller: Annotated[Caller, Depends(current_caller)],
    ) -> Caller:
        if caller.roles.isdisjoint(roles):
            log.info("refused not_allowed: user %s", caller.user.id)
            raise refuse(403, "not_allowed")
        return caller

    return caller_with_role


# Staff roles (UC-14, auth-layer §3.4), for POST /staff and grant_das.py; folded in
# from staff/ (ADR-005). `user_for` also makes the user rows behind senior and
# caregiver grants (UC-01).

STAFF_ROLES = (Role.das, Role.medic)

# One lock for the writes that count or clear across all DAS rows: it serializes the
# last-das check (Q6) and the one-on-duty switch (P10), whose race on the partial unique
# index on on_duty would otherwise be a 500.
STAFF_LOCK = 20261016

# The staff refusals keep the logger they had before staff/ was folded in (ADR-005).
staff_log = logging.getLogger("echocare.staff")


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


async def new_grant(
    session: AsyncSession, phone_e164: str, display_name: str, **grant: Any
) -> User | None:
    """The number's user, made if it has none, with a new grant of the `grant` columns;
    None when the number already held it. No conflict target: covers every unique index
    on grants. Doesn't commit."""
    user = await user_for(session, phone_e164, display_name)
    granted = await session.scalar(
        insert(Grant)
        .values(user_id=user.id, **grant)
        .on_conflict_do_nothing()
        .returning(Grant.id)
    )
    return None if granted is None else user


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
    user = await new_grant(
        session, phone_e164, display_name, role=role, granted_by=granted_by
    )
    if user is None:
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
        staff_log.info("refused not_found: staff %s", user_id)
        raise refuse(404, "not_found")
    if form.practice is not None and Role.medic not in roles:
        staff_log.info("refused not_medic: staff %s", user_id)
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
            staff_log.info("refused wrong_state: last das %s", user_id)
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
        staff_log.info("refused not_allowed: on duty %s holds no das grant", user_id)
        await session.rollback()
        raise refuse(403, "not_allowed")
    await session.execute(update(User).where(User.on_duty).values(on_duty=False))
    if user_id is not None:
        await session.execute(
            update(User).where(User.id == user_id).values(on_duty=True)
        )
    await session.commit()


async def on_duty(session: AsyncSession) -> tuple[uuid.UUID, str] | None:
    """The on-duty DAS employee's id and phone, read at hand-over time (06 §4); None
    when nobody is on duty."""
    row = (
        await session.execute(select(User.id, User.phone_e164).where(User.on_duty))
    ).first()
    return None if row is None else (row.id, row.phone_e164)


# What `seniors` writes in `auth`'s tables, transaction-neutral: these don't commit and
# report failure in their return value (ADR-005).


async def sync_senior_grant(
    session: AsyncSession,
    senior_id: uuid.UUID,
    phone_e164: str,
    display_name: str,
    *,
    landline: bool,
    granted_by: uuid.UUID,
) -> bool:
    """A mobile number is the senior's own grant; a landline has none (UC-01 step 3).

    A changed number drops the old number's grant. Returns whether the senior holds
    its number's grant afterwards: `True` for a landline, `False` when the number
    already holds another senior's, which the caller refuses as `phone_taken` (SE10).
    """
    await session.execute(
        delete(Grant).where(
            Grant.senior_id == senior_id,
            Grant.role == Role.senior,
            Grant.user_id.not_in(select(User.id).where(User.phone_e164 == phone_e164)),
        )
    )
    if landline:
        return True
    user = await user_for(session, phone_e164, display_name)
    # No conflict target: covers both the per-senior key and the SE10 index.
    await session.execute(
        insert(Grant)
        .values(
            user_id=user.id,
            role=Role.senior,
            senior_id=senior_id,
            granted_by=granted_by,
        )
        .on_conflict_do_nothing()
    )
    return await session.scalar(
        select(
            select(Grant.id)
            .where(
                Grant.user_id == user.id,
                Grant.senior_id == senior_id,
                Grant.role == Role.senior,
            )
            .exists()
        )
    )


async def add_caregiver_grant(
    session: AsyncSession,
    senior_id: uuid.UUID,
    phone_e164: str,
    display_name: str,
    relation: str,
    granted_by: uuid.UUID,
) -> User | None:
    """A caregiver grant for the number, making its user row if it has none (UC-01).

    None when the number already holds this senior's caregiver grant: the caller
    rolls back, which also drops a user row made here.
    """
    return await new_grant(
        session,
        phone_e164,
        display_name,
        role=Role.caregiver,
        senior_id=senior_id,
        relation=relation,
        granted_by=granted_by,
    )


async def edit_caregiver_grant(
    session: AsyncSession,
    user: User,
    grant: Grant,
    *,
    display_name: str | None,
    relation: str | None,
) -> bool:
    """The caregiver's name (everywhere, Q13) and relation; what is None stays.

    False, with nothing changed, when the name would change on a das or medic: a staff
    member's name is theirs to change, through PATCH /staff/{userId} (Q22).
    """
    if display_name is not None:
        staff = select(Grant.id).where(
            Grant.user_id == user.id, Grant.role.in_(STAFF_ROLES)
        )
        if await session.scalar(select(staff.exists())):
            return False
        user.display_name = display_name
    if relation is not None:
        grant.relation = relation
    return True


async def revoke_caregiver_grant(
    session: AsyncSession, senior_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Deletes the caregiver grant; none is fine."""
    await session.execute(
        delete(Grant).where(
            Grant.senior_id == senior_id,
            Grant.user_id == user_id,
            Grant.role == Role.caregiver,
        )
    )
