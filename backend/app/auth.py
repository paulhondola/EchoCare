"""Who is calling (01 §6): verify the Firebase token, then find the number's grants.

The refusals and their reasons are auth-layer §3.2; the steps are auth-layer §3.1.
"""

import json
import logging
from dataclasses import dataclass
from typing import Annotated, Any

import firebase_admin
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import ROLE_ORDER, Grant, Role, User
from app.phones import mask, normalize

log = logging.getLogger("sentinela.auth")

# auto_error=False: a missing or non-Bearer header gets our own 401 body. It also
# gives Swagger its Authorize button.
bearer = HTTPBearer(auto_error=False)

_firebase: firebase_admin.App | None = None


def refuse(status: int, reason: str) -> HTTPException:
    """A refusal in the shape every client parses: {"detail": {"reason": ...}}."""
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return HTTPException(status, {"reason": reason}, headers=headers)


def init_firebase(service_account: str | None) -> None:
    """Starts the Admin SDK once, when this machine has the key (auth-layer AL11)."""
    global _firebase
    if not service_account:
        log.warning(
            "FIREBASE_SERVICE_ACCOUNT is not set: protected requests answer 503"
        )
        return
    if _firebase is not None:
        return
    try:
        info = json.loads(service_account)
    except json.JSONDecodeError:
        raise SystemExit(
            "FIREBASE_SERVICE_ACCOUNT is not valid JSON: paste the key file's content "
            "on one line, in single quotes"
        ) from None
    _firebase = firebase_admin.initialize_app(credentials.Certificate(info))


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
    if _firebase is None:
        raise refuse(503, "auth_unavailable")
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
