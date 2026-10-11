"""Fixtures. Tests that need the database ask for `db`; the rest run without one."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

# Before anything imports app: app.db builds its engine from DATABASE_URL at import, and
# an environment variable beats backend/.env. Tests never use `sentinela` (AGENTS.md).
os.environ["DATABASE_URL"] = (
    "postgresql://sentinela:sentinela@localhost:5432/sentinela_test"
)

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Session, engine
from app.models import Grant, Role, User

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
