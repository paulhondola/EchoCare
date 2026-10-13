"""Fixtures. Tests that need the database ask for `db` or `client`; the rest run without."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

# Before anything imports app: app.db builds its engine from DATABASE_URL at import, and
# an environment variable beats backend/.env. Tests never use `sentinela` (AGENTS.md).
os.environ["DATABASE_URL"] = (
    "postgresql://sentinela:sentinela@localhost:5432/sentinela_test"
)
# Twilio's callbacks are signed with this token for the address Twilio would call (#15).
os.environ["TWILIO_AUTH_TOKEN"] = "test-auth-token"
os.environ["PUBLIC_BASE_URL"] = "https://sentinela.test"

import pytest
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import bearer, refuse, verify_token
from app.core.db import Session, engine
from app.main import app
from app.models import Grant, Role, Senior, User

BACKEND = Path(__file__).parent.parent


def alembic(*args: str) -> None:
    # A child process: alembic/env.py runs its own event loop with asyncio.run.
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, check=True)


@pytest.fixture(scope="session")
def migrated() -> None:
    alembic("downgrade", "base")  # so every run also proves the downgrade
    alembic("upgrade", "head")


@pytest.fixture
async def db(migrated: None) -> AsyncIterator[AsyncSession]:
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE grants, users CASCADE"))
    async with Session() as session:
        yield session


@pytest.fixture
def add_user(db: AsyncSession) -> Callable[..., Awaitable[User]]:
    """add_user("+40700000001", Role.das): a user with staff grants, straight in the db."""

    async def add(phone: str, *roles: Role, name: str = "Test") -> User:
        user = User(phone_e164=phone, display_name=name)
        db.add(user)
        await db.flush()  # the database makes the id
        db.add_all(Grant(user_id=user.id, role=role) for role in roles)
        await db.commit()
        return user

    return add


@pytest.fixture
def add_senior(
    db: AsyncSession, add_user: Callable[..., Awaitable[User]]
) -> Callable[..., Awaitable[Senior]]:
    """add_senior("+40700000101"): a draft senior registered by a fresh medic, which
    caregiver and senior grants can name now that grants.senior_id has its key (AL6)."""

    async def add(phone: str, name: str = "Maria Pop") -> Senior:
        medic = await add_user(f"+4079{phone[-7:]}", Role.medic, name="Medic")
        senior = Senior(
            medic_id=medic.id,
            full_name=name,
            form_of_address="doamna Maria",
            phone_e164=phone,
            phone_is_landline=False,
        )
        db.add(senior)
        await db.commit()
        return senior

    return add


def fake_verify_token(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict[str, Any]:
    """The stand-in verifier (06 §5). The token is the phone number, optionally
    followed by |uid; "invalid" and "no-phone" act out the two broken tokens."""
    if creds is None or creds.credentials == "invalid":
        raise refuse(401, "not_signed_in")
    if creds.credentials == "no-phone":
        return {"uid": "no-phone"}
    phone, _, uid = creds.credentials.partition("|")
    return {"uid": uid or f"uid-{phone}", "phone_number": phone}


@pytest.fixture
async def client(db: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[verify_token] = fake_verify_token
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
