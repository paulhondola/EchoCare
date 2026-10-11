"""Who is calling (01 §6): verify the Firebase token, then find the number's grants.

The refusals and their reasons are auth-layer §3.2; the steps are auth-layer §3.1.
"""

import json
import logging
from typing import Annotated, Any

import firebase_admin
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials

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
