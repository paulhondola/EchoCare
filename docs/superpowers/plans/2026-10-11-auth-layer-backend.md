# Auth layer, backend slice: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FastAPI verifies Firebase phone sign-in tokens and decides what each caller may do from grants in its own database. It serves `GET /api/me` and `POST /api/staff`, and ships the `grant_das.py` and `dev_token.py` scripts.

**Architecture:**
- A `verify_token` dependency checks the Firebase token. It is a plain `def`, so FastAPI runs it in the thread pool.
- `current_caller` turns the token's `phone_number` claim into a user and their grants, in one query.
- `require_roles(...)` checks the union of the caller's roles.
- `grant_staff()` is shared by the endpoint and the setup script. It uses `INSERT … ON CONFLICT DO NOTHING`, so two simultaneous grants cannot both win.
- One Alembic migration creates `users` and `grants`. Postgres 18's `uuidv7()` makes the ids.

**Tech stack:** Python 3.14, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, Postgres 18, firebase-admin, phonenumbers, pytest with pytest-asyncio and httpx, uv, ruff.

**Spec:** [docs/specs/auth-layer.md](../../specs/auth-layer.md), sections 1 to 6. Read §1 to §5 before Task 1; §6 is the backend brief this plan implements.

**This code was run before the plan was written.** Every code block below was run in a scratch copy of `backend/` against Compose's Postgres 18:
- 62 tests pass.
- `ruff check` and `ruff format --check` (ruff 0.16.10, the repository's defaults) are clean.
- `alembic check` reports no difference between the models and the migration.

If a step's expected output differs, look for a difference in the environment before changing the code.

## Global Constraints

- Work on the branch `auth-layer`, from the repository root `/Users/paulhondola/Developer/Sentinela-Test`. Every `uv` command runs from `backend/`.
- **Database:** Compose's Postgres must be running (`docker compose up -d db`), and `sentinela_test` must exist. On a volume created before Compose's init script, create it once with `docker compose exec db createdb -U sentinela sentinela_test`. Tests never use `sentinela`.
- **Commits run tests:** lefthook's pre-commit runs `ruff check --fix`, `ruff format` and `uv run pytest -q` whenever backend files are staged, so the database must be up when you commit.
- **Refusal body:** exactly `{"detail": {"reason": "<reason>"}}`. The reasons are exactly `not_signed_in` (401, with `WWW-Authenticate: Bearer`), `not_registered` (403), `not_allowed` (403), `already_done` (409) and `auth_unavailable` (503).
- **Phone numbers:** stored and compared as E.164, parsed with `phonenumbers` using the default region `RO`.
- **Logs** never contain a token or a full phone number. A number is written masked, as `+40700***009`.
- **Comments cite the spec** by ID (`auth-layer AL4`, `auth-layer §3.2`, `04 §0`, `G6`), as the root `AGENTS.md` asks.
- **Migrations and API changes only add** (ADR-001 §2.3). This plan's migration is the first one.
- **Every route** goes on the `api` router, declared before `app.include_router(api)` at the bottom of `main.py`.
- **Cloud environments are off limits:** no `railway config apply`, no `railway variable set`, no deploys. Push and open a PR only when the person asks.
- **Commit messages** start with `backend:` or `docs:` and end with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

Inputs the spec implies, each pinned by a test in the task that owns the code:

1. **A number typed one way at grant time** (`0700 000 002`) and reported in E.164 by Firebase (`+40700000002`) must resolve to the same user. Pinned by `test_the_new_medic_signs_in` (Task 5).
2. **A malformed `FIREBASE_SERVICE_ACCOUNT`**, for example pasted across several lines or without quotes, must stop startup with a message naming the variable, not a stack trace. Pinned by `test_key_that_is_not_json_stops_startup` (Task 3).
3. **A display name or practice of only spaces** is refused with a 422 and never stored. Pinned by `test_invalid_bodies` (Task 5).
4. **Granting DAS to an existing medic** keeps their practice. Pinned by `test_a_das_grant_keeps_the_practice` (Task 5).
5. **An `Authorization` header with another scheme** (`Basic …`) is a 401 with the standard body, not a 403 or a 500. Pinned by `test_not_signed_in[headers1]` (Task 4).

---

### Task 1: Phone numbers

**Files:**
- Create: `backend/app/phones.py`
- Create: `backend/tests/test_phones.py`
- Modify: `backend/pyproject.toml`, `backend/uv.lock` (through `uv add`)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `normalize(raw: str) -> str` returns E.164 and raises `ValueError` for anything invalid.
  - `is_mobile(e164: str) -> bool` is true for numbers that can receive an SMS.
  - `mask(e164: str) -> str` returns `+40700***009`.

- [ ] **Step 1: Add the dependency**

Run: `cd backend && uv add phonenumbers`
Expected: `pyproject.toml` lists `phonenumbers>=…` under `dependencies`.

- [ ] **Step 2: Write the failing test**

`backend/tests/test_phones.py`:

```python
import pytest

from app.phones import is_mobile, mask, normalize


@pytest.mark.parametrize(
    ("raw", "e164"),
    [
        ("0722 123 456", "+40722123456"),
        ("+40722123456", "+40722123456"),
        ("0040 722 123 456", "+40722123456"),
        ("(0722) 123-456", "+40722123456"),
        ("0700 000 002", "+40700000002"),  # a Firebase test number (auth-layer §5)
        ("0256 123 456", "+40256123456"),  # Timișoara landline
        ("+16505550101", "+16505550101"),
    ],
)
def test_normalize(raw, e164):
    assert normalize(raw) == e164


@pytest.mark.parametrize("raw", ["12345", "", "not a number", "+40 1"])
def test_normalize_refuses(raw):
    with pytest.raises(ValueError):
        normalize(raw)


def test_is_mobile():
    assert is_mobile("+40722123456")
    assert is_mobile("+40700000001")
    assert is_mobile("+16505550101")  # FIXED_LINE_OR_MOBILE: can receive an SMS
    assert not is_mobile("+40256123456")


def test_mask():
    assert mask("+40700000009") == "+40700***009"
```

- [ ] **Step 3: Run it to see it fail**

Run: `uv run pytest tests/test_phones.py -q`
Expected: an error at collection, `ModuleNotFoundError: No module named 'app.phones'`.

- [ ] **Step 4: Implement**

`backend/app/phones.py`:

```python
"""Phone numbers in one international format (04 §0), Romania by default (auth-layer §3.5)."""

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType

# Staff sign in by SMS, so their numbers must be able to receive one (auth-layer AL12).
SMS_TYPES = {PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE}


def normalize(raw: str) -> str:
    """E.164 for a number as typed or as Firebase reports it; ValueError if not valid."""
    try:
        number = phonenumbers.parse(raw, "RO")
    except NumberParseException:
        raise ValueError("not a phone number") from None
    if not phonenumbers.is_valid_number(number):
        raise ValueError("not a valid phone number")
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def is_mobile(e164: str) -> bool:
    return phonenumbers.number_type(phonenumbers.parse(e164)) in SMS_TYPES


def mask(e164: str) -> str:
    """A number as it may appear in logs (auth-layer AL15): +40700***009."""
    return f"{e164[:6]}***{e164[-3:]}"
```

- [ ] **Step 5: Run it to see it pass**

Run: `uv run pytest tests/test_phones.py -q`
Expected: `13 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/phones.py backend/tests/test_phones.py backend/pyproject.toml backend/uv.lock
git commit -m "backend: normalize phone numbers to E.164 (auth-layer §3.5)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Tables, migration and the database test harness

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/alembic/versions/5d0c8c3a7f21_users_and_grants.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_models.py`
- Modify: `backend/app/db.py` (full replacement below)
- Modify: `backend/alembic/env.py` (the import block)
- Modify: `backend/pyproject.toml`, `backend/uv.lock` (`uv add --dev`, then the pytest options)
- Modify: `.github/workflows/backend.yml` (the `jobs:` block)
- Modify: `backend/README.md` (one paragraph)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `app.db`: `Base`, `engine`, `Session` (an `async_sessionmaker` with `expire_on_commit=False`), and `get_session() -> AsyncIterator[AsyncSession]`.
  - `app.models`:
    - `Role(StrEnum)`, with the values `das`, `medic`, `caregiver`, `senior`.
    - `ROLE_ORDER: list[Role]`, in that order.
    - `User`: `id`, `phone_e164`, `display_name`, `firebase_uid`, `practice`, `created_at`.
    - `Grant`: `id`, `user_id`, `role: str`, `senior_id`, `relation`, `granted_by`, `created_at`.
  - Test fixtures:
    - `migrated`, scoped to the session.
    - `db`, an `AsyncSession` over freshly emptied tables.
    - `add_user`, an async factory: `await add_user(phone, *roles, name="Test") -> User`.

- [ ] **Step 1: Add the test dependencies and pytest options**

Run: `uv add --dev pytest-asyncio httpx`

In `backend/pyproject.toml`, replace

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

with

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
# One event loop for the whole run: app.db's module-level engine pools asyncpg
# connections, which belong to the loop that opened them (auth-layer §6.2).
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
```

- [ ] **Step 2: Write the harness and the failing test**

`backend/tests/conftest.py`:

```python
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
```

`backend/tests/test_models.py`:

```python
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Grant, Role

BACKEND = Path(__file__).parent.parent


def test_models_match_the_migration(migrated):
    # `alembic check` fails when autogenerate would add anything (auth-layer §4).
    subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=BACKEND, check=True)


async def test_ids_are_uuid_v7(add_user):
    user = await add_user("+40700000001")
    assert user.id.version == 7


async def test_one_grant_per_role(db, add_user):
    user = await add_user("+40700000001", Role.das)
    db.add(Grant(user_id=user.id, role=Role.das))
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.parametrize(
    ("role", "senior_id"),
    [
        (Role.caregiver, None),  # a caregiver grant names its senior
        (Role.senior, None),
        (Role.das, uuid.uuid4()),  # a staff grant names none
        ("boss", None),  # only the four roles
    ],
)
async def test_grant_checks(db, add_user, role, senior_id):
    user = await add_user("+40700000001")
    db.add(Grant(user_id=user.id, role=role, senior_id=senior_id))
    with pytest.raises(IntegrityError):
        await db.commit()
```

- [ ] **Step 3: Run it to see it fail**

Run: `uv run pytest tests/test_models.py -q`
Expected: an error loading `conftest.py`, `ImportError: cannot import name 'Session' from 'app.db'`.

- [ ] **Step 4: Implement the session, the models and the migration**

Replace all of `backend/app/db.py` with:

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.settings import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
# expire_on_commit=False: rows stay readable after a commit, since async code cannot
# lazy-load an expired attribute.
Session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """One session per request; FastAPI hands the same one to every dependency."""
    async with Session() as session:
        yield session
```

`backend/app/models.py`:

```python
"""Tables (05), only those the built features use: the auth layer's (auth-layer §4).

The database makes every row id with uuidv7(), built into Postgres 18 (04 §0).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Role(StrEnum):
    das = "das"
    medic = "medic"
    caregiver = "caregiver"
    senior = "senior"


# The order of GET /me's grants (auth-layer §3.3).
ROLE_ORDER = list(Role)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=text("uuidv7()"))


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """One row per phone number granted anything, made before first sign-in (05 §4)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Its unique index serves the lookup on every request (auth-layer §3.1).
    phone_e164: Mapped[str] = mapped_column(String(16), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    # Replaced, with a warning, if another Firebase account signs in with the number (AL4).
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True)
    practice: Mapped[str | None] = mapped_column(String(200))  # medics
    created_at: Mapped[datetime] = created_at()


class Grant(Base):
    """One role for one user; caregiver and senior grants name their senior (AL5)."""

    __tablename__ = "grants"
    __table_args__ = (
        # NULLS NOT DISTINCT: a das or medic grant, whose senior_id is NULL, is also
        # unique per user. Starting with user_id, it serves the per-request grant lookup.
        UniqueConstraint(
            "user_id", "role", "senior_id", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint(
            "role IN ('das', 'medic', 'caregiver', 'senior')", name="role_known"
        ),
        CheckConstraint(
            "(role IN ('caregiver', 'senior')) = (senior_id IS NOT NULL)",
            name="senior_only_for_senior_roles",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Revoking a grant deletes it, so access stops at once (05 §5).
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    # No foreign key until the seniors table exists (AL6).
    senior_id: Mapped[uuid.UUID | None]
    relation: Mapped[str | None] = mapped_column(String(60))  # caregivers
    # Empty for grants made by the setup script (G6).
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at()
```

In `backend/alembic/env.py`, replace

```python
from alembic import context
from app.db import Base
from app.settings import db_host, get_settings, is_local_db, on_railway
```

with

```python
import app.models  # noqa: F401  # autogenerate and check see only imported tables
from alembic import context
from app.db import Base
from app.settings import db_host, get_settings, is_local_db, on_railway
```

`backend/alembic/versions/5d0c8c3a7f21_users_and_grants.py`. It is written by hand from a verified autogenerate render; `test_models_match_the_migration` proves that it and the models agree.

```python
"""users and grants

Revision ID: 5d0c8c3a7f21
Revises:
Create Date: 2026-10-11 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d0c8c3a7f21"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("phone_e164", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("firebase_uid", sa.String(length=128), nullable=True),
        sa.Column("practice", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("firebase_uid"),
        sa.UniqueConstraint("phone_e164"),
    )
    op.create_table(
        "grants",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("senior_id", sa.Uuid(), nullable=True),
        sa.Column("relation", sa.String(length=60), nullable=True),
        sa.Column("granted_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(role IN ('caregiver', 'senior')) = (senior_id IS NOT NULL)",
            name="senior_only_for_senior_roles",
        ),
        sa.CheckConstraint(
            "role IN ('das', 'medic', 'caregiver', 'senior')", name="role_known"
        ),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "role", "senior_id", postgresql_nulls_not_distinct=True
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("grants")
    op.drop_table("users")
```

- [ ] **Step 5: Run it to see it pass**

Run: `uv run pytest -q`
Expected: `24 passed`. That is the 4 existing settings tests, 13 phone tests and 7 model tests: `test_models_match_the_migration`, `test_ids_are_uuid_v7` and `test_one_grant_per_role` 1 each, plus 4 cases of `test_grant_checks`.

Then confirm the table by hand:

Run: `docker compose exec -T db psql -U sentinela -d sentinela_test -c '\d grants'`
Expected: the output shows `UNIQUE CONSTRAINT, btree (user_id, role, senior_id) NULLS NOT DISTINCT`, both CHECK constraints `role_known` and `senior_only_for_senior_roles`, and `grants_user_id_fkey … ON DELETE CASCADE`.

- [ ] **Step 6: Run the database in CI**

In `.github/workflows/backend.yml`, replace

```yaml
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
```

with

```yaml
jobs:
  check:
    runs-on: ubuntu-latest
    # tests/conftest.py points at sentinela_test on localhost (auth-layer §6.4)
    services:
      postgres:
        image: postgres:18 # the major version of Railway's Postgres and Compose's
        env:
          POSTGRES_USER: sentinela
          POSTGRES_PASSWORD: sentinela
          POSTGRES_DB: sentinela_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U sentinela"
          --health-interval 2s
          --health-retries 15
    steps:
```

- [ ] **Step 7: Document the test database**

In `backend/README.md`, replace

```markdown
Tests that need a database use `sentinela_test`, which Compose creates on a fresh volume, never `sentinela`.
```

with

````markdown
Tests that need a database use `sentinela_test`, never `sentinela`, so Compose's `db` must be running. Each run migrates it down and up again, so it also proves the migrations. Compose creates `sentinela_test` on a fresh volume; on an older one, create it once:

```bash
docker compose exec db createdb -U sentinela sentinela_test
```
````

- [ ] **Step 8: Commit**

```bash
git add backend/app/db.py backend/app/models.py backend/alembic/env.py backend/alembic/versions/5d0c8c3a7f21_users_and_grants.py backend/tests/conftest.py backend/tests/test_models.py backend/pyproject.toml backend/uv.lock backend/README.md .github/workflows/backend.yml
git commit -m "backend: add the users and grants tables (auth-layer §4)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Firebase verifier and startup checks

**Files:**
- Create: `backend/app/auth.py` (the verifier; Task 4 extends it)
- Create: `backend/tests/test_verify.py`
- Modify: `backend/app/settings.py`, `backend/app/main.py` (full replacement below), `backend/tests/test_settings.py`
- Modify: `backend/pyproject.toml`, `backend/uv.lock` (`uv add`)
- Modify (docs and config): `backend/.env.example`, `backend/README.md`, `docs/adr/ADR-001-monorepo-and-delivery.md`, `.railway/railway.ts`, `docs/specs/sentinela/04-interfaces.md` §0, `docs/specs/sentinela/06-operations.md` §4

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `app.settings`: `Settings.firebase_service_account: str | None`, and `check_firebase(settings) -> None`, which raises `SystemExit` on Railway without the key.
  - `app.auth`:
    - `log`, the logger `sentinela.auth`.
    - `bearer`, an `HTTPBearer(auto_error=False)`.
    - `refuse(status: int, reason: str) -> HTTPException`.
    - `init_firebase(service_account: str | None) -> None`.
    - `verify_token(creds) -> dict[str, Any]`, a plain `def` dependency that returns the claims.

- [ ] **Step 1: Add the dependency**

Run: `uv add firebase-admin`

- [ ] **Step 2: Write the failing tests**

`backend/tests/test_verify.py`:

```python
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from firebase_admin import auth as fb

from app import auth

TOKEN = HTTPAuthorizationCredentials(scheme="Bearer", credentials="a.b.c")


def refusal(e: pytest.ExceptionInfo[HTTPException]) -> tuple[int, str]:
    return e.value.status_code, e.value.detail["reason"]


@pytest.fixture
def firebase(monkeypatch):
    """A started Admin SDK whose verify_id_token answers what the test says."""
    monkeypatch.setattr(auth, "_firebase", object())

    def answer(result):
        def verify_id_token(token, app):
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(fb, "verify_id_token", verify_id_token)

    return answer


def test_no_token_is_not_signed_in():
    with pytest.raises(HTTPException) as e:
        auth.verify_token(None)
    assert refusal(e) == (401, "not_signed_in")
    assert e.value.headers == {"WWW-Authenticate": "Bearer"}


def test_no_key_is_unavailable(monkeypatch):
    monkeypatch.setattr(auth, "_firebase", None)
    with pytest.raises(HTTPException) as e:
        auth.verify_token(TOKEN)
    assert refusal(e) == (503, "auth_unavailable")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (fb.ExpiredIdTokenError("expired", cause=None), (401, "not_signed_in")),
        (fb.InvalidIdTokenError("wrong signature"), (401, "not_signed_in")),
        (ValueError("not a token"), (401, "not_signed_in")),
        (fb.CertificateFetchError("no keys", cause=None), (503, "auth_unavailable")),
    ],
)
def test_errors(firebase, error, expected):
    firebase(error)
    with pytest.raises(HTTPException) as e:
        auth.verify_token(TOKEN)
    assert refusal(e) == expected


def test_claims_pass_through(firebase):
    firebase({"uid": "u1", "phone_number": "+40700000001"})
    assert auth.verify_token(TOKEN) == {"uid": "u1", "phone_number": "+40700000001"}


def test_key_that_is_not_json_stops_startup(monkeypatch):
    monkeypatch.setattr(auth, "_firebase", None)
    with pytest.raises(SystemExit, match="not valid JSON"):
        auth.init_firebase("{not json")
```

In `backend/tests/test_settings.py`, replace the import line

```python
from app.settings import Settings, check_environment, is_local_db
```

with

```python
from app.settings import Settings, check_environment, check_firebase, is_local_db
```

and append to the end of the file:

```python


def test_firebase_key_required_on_railway(monkeypatch):
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "dep-1")
    # passed explicitly: a laptop's backend/.env may hold the key
    with pytest.raises(SystemExit, match="FIREBASE_SERVICE_ACCOUNT"):
        check_firebase(Settings(database_url=LOCAL, firebase_service_account=None))
    check_firebase(Settings(database_url=LOCAL, firebase_service_account="{}"))


def test_firebase_key_optional_on_a_laptop(monkeypatch):
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    check_firebase(Settings(database_url=LOCAL, firebase_service_account=None))
```

- [ ] **Step 3: Run them to see them fail**

Run: `uv run pytest tests/test_verify.py tests/test_settings.py -q`
Expected: collection errors, `cannot import name 'auth' from 'app'` and `cannot import name 'check_firebase'`.

- [ ] **Step 4: Implement the setting, the check and the verifier**

In `backend/app/settings.py`, replace

```python
    demo_mode: bool = True
```

with

```python
    demo_mode: bool = True
    # The Firebase Admin SDK service account: the key file's JSON on one line
    # (auth-layer AL11). Without it a laptop starts, and protected requests answer 503.
    firebase_service_account: str | None = None
```

and replace

```python
@lru_cache
def get_settings() -> Settings:
```

with

```python
def check_firebase(settings: Settings) -> None:
    """On Railway, refuse to start without the service account (auth-layer AL11).

    The health check then fails and Railway keeps the previous deploy serving.
    """
    if on_railway() and not settings.firebase_service_account:
        raise SystemExit("Refusing to start: FIREBASE_SERVICE_ACCOUNT is not set.")


@lru_cache
def get_settings() -> Settings:
```

`backend/app/auth.py`:

```python
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
    except (auth.InvalidIdTokenError, ValueError):
        # InvalidIdTokenError covers expired and wrongly signed tokens, ValueError one
        # that is not a token at all; neither class derives from the other.
        log.info("refused not_signed_in: invalid token")
        raise refuse(401, "not_signed_in") from None
```

Replace all of `backend/app/main.py` with:

```python
import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.auth import init_firebase
from app.db import engine
from app.settings import check_environment, check_firebase, get_settings

# Our own loggers at INFO, for refusals (auth-layer AL15); uvicorn sets up only its own.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("sentinela").setLevel(logging.INFO)

settings = get_settings()
check_environment(settings)
check_firebase(settings)
init_firebase(settings.firebase_service_account)

# Everything under /api, docs included, so the API and the dashboard can share one domain.
app = FastAPI(
    title="Sentinela",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
# Browser requests only from the dashboard's own address (01 §4, channel 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api")


@api.get("/health")
async def health() -> dict[str, str]:
    # Fails when the database is unreachable, so Railway holds back a broken deploy (06 §1).
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "env": settings.app_env}


# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)
```

- [ ] **Step 5: Run them to see them pass**

Run: `uv run pytest -q`
Expected: all pass. That's 24 from before, plus 8 in `test_verify.py` (1 + 1 + 4 + 1 + 1) and 2 new in `test_settings.py`: 34.

- [ ] **Step 6: Document the variable and declare it for Railway**

Append to `backend/.env.example`:

```
# Firebase Admin SDK service account (docs/specs/auth-layer.md AL11): the laptop key from
# the team password manager, the key file's JSON on one line in single quotes. Empty:
# the API starts and protected requests answer 503.
FIREBASE_SERVICE_ACCOUNT=
```

In `backend/README.md`'s variables table, after the row

```markdown
| `DEMO_MODE` | `true` | Shortens timers for the demo (06 §3) |
```

add

```markdown
| `FIREBASE_SERVICE_ACCOUNT` | the laptop key from the team password manager, its JSON on one line in single quotes | Verifies sign-in tokens. Without it the API starts and protected requests answer 503; on Railway the API refuses to start |
```

In `docs/adr/ADR-001-monorepo-and-delivery.md`'s "Variables tie the services together" table, after the `PUBLIC_BASE_URL` row add:

```markdown
| `FIREBASE_SERVICE_ACCOUNT` | `api` | Secret: the Firebase Admin SDK service account's JSON, set with `railway variable set` and declared with `preserve()` ([auth-layer.md](../specs/auth-layer.md) AL11, §9) |
```

In `.railway/railway.ts`, replace

```ts
import { defineRailway, github, postgres, project, service } from "railway/iac";
```

with

```ts
import { defineRailway, github, postgres, preserve, project, service } from "railway/iac";
```

and replace

```ts
      ALLOWED_ORIGIN: "https://${{dashboard.RAILWAY_PUBLIC_DOMAIN}}",
    },
```

with

```ts
      ALLOWED_ORIGIN: "https://${{dashboard.RAILWAY_PUBLIC_DOMAIN}}",
      // Secret, set with `railway variable set` (docs/specs/auth-layer.md §9);
      // preserve() keeps it when this file is applied.
      FIREBASE_SERVICE_ACCOUNT: preserve(),
    },
```

`preserve` is exported by `railway/iac`; this was checked in `.railway/node_modules`. A person applies this file (§9 of the spec). If the Railway CLI is logged in, you may run the read-only `railway config plan --environment staging` from `.railway/` and include its output in your report. Never apply.

- [ ] **Step 7: Update the contract's conventions and the privacy table**

In `docs/specs/sentinela/04-interfaces.md` §0, replace

```markdown
- **Identity.** Every request from the Android app or the dashboard carries its Firebase identity token. FastAPI verifies it, reads the phone number and loads the caller's grants. A request without a valid token is refused.
```

with

```markdown
- **Identity.** Every request from the Android app or the dashboard carries its Firebase identity token as `Authorization: Bearer <token>`. FastAPI verifies it, reads the phone number and loads the caller's grants. A request without a valid token is refused. The caller may do what any of their grants allows ([auth-layer.md](../auth-layer.md) AL2).
```

and replace

```markdown
- **Refusals.** A refused request says why in a short machine-readable reason: not signed in, not allowed, not found, wrong state, already done.
```

with

```markdown
- **Refusals.** A refused request says why in a short machine-readable reason, as `{"detail": {"reason": "…"}}`: `not_signed_in` (401), `not_registered` (403, a number with no grant), `not_allowed` (403), `not_found` (404, also for a senior outside the caller's reach), `wrong_state` and `already_done` (409), `auth_unavailable` (503, sign-in cannot be checked right now). [auth-layer.md](../auth-layer.md) §3.2 says what a client does with each.
```

In `docs/specs/sentinela/06-operations.md` §4's **Access** table, after the row

```markdown
| The on-duty number | The on-duty DAS employee's own phone, read at hand-over time; only a DAS user can change who is on duty |
```

add

```markdown
| Logs | A refusal is logged with its reason and the user id, or a masked number (`+40700***009`). Tokens are never logged ([auth-layer.md](../auth-layer.md) AL15) |
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/auth.py backend/app/settings.py backend/app/main.py backend/tests/test_verify.py backend/tests/test_settings.py backend/pyproject.toml backend/uv.lock backend/.env.example backend/README.md docs/adr/ADR-001-monorepo-and-delivery.md .railway/railway.ts docs/specs/sentinela/04-interfaces.md docs/specs/sentinela/06-operations.md
git commit -m "backend: verify Firebase identity tokens (auth-layer §3.1, AL10, AL11)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: The caller and `GET /api/me`

**Files:**
- Modify: `backend/app/auth.py` (full replacement below)
- Modify: `backend/app/main.py` (full replacement below)
- Modify: `backend/tests/conftest.py` (full replacement below)
- Create: `backend/tests/test_me.py`
- Modify (docs): `docs/specs/sentinela/04-interfaces.md` §1, `docs/specs/sentinela/01-architecture.md` §6, `docs/specs/sentinela/02-use-cases.md` UC-02, `docs/specs/sentinela/05-data-model.md` §3 and §4

**Interfaces:**
- Consumes:
  - From Task 1: `normalize`, `mask`.
  - From Task 2: `get_session`, `User`, `Grant`, `Role`, `ROLE_ORDER`, and the `db` and `add_user` fixtures.
  - From Task 3: `refuse`, `verify_token`, `bearer`, `log`.
- Produces:
  - `app.auth.Caller`, a frozen dataclass with `user: User`, `grants: list[Grant]` and `roles -> set[Role]`.
  - `current_caller`, an async dependency that returns a `Caller`.
  - `require_roles(*roles: Role)`, which returns an async dependency that returns a `Caller`.
  - The route `GET /api/me`.
  - The test fixture `client`, an `httpx.AsyncClient` with the stand-in verifier. A token is `"<phone>"` or `"<phone>|<uid>"`; the special tokens `"invalid"` and `"no-phone"` act out broken ones.

- [ ] **Step 1: Write the stand-in verifier, the client fixture and the failing tests**

Replace all of `backend/tests/conftest.py` with:

```python
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

import pytest
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import bearer, refuse, verify_token
from app.db import Session, engine
from app.main import app
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
```

`backend/tests/test_me.py`:

```python
import logging
import uuid

import pytest
from sqlalchemy import select

from app.models import Grant, Role, User

DAS = "+40700000001"
NOT_SIGNED_IN = {"detail": {"reason": "not_signed_in"}}
NOT_REGISTERED = {"detail": {"reason": "not_registered"}}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic abc"},  # another scheme is no token at all
        signed_in("invalid"),
        signed_in("no-phone"),
    ],
)
async def test_not_signed_in(client, headers):
    r = await client.get("/api/me", headers=headers)
    assert (r.status_code, r.json()) == (401, NOT_SIGNED_IN)
    assert r.headers["www-authenticate"] == "Bearer"


async def test_unknown_number(client, caplog):
    caplog.set_level(logging.INFO, logger="sentinela.auth")
    r = await client.get("/api/me", headers=signed_in("+40700000009"))
    assert (r.status_code, r.json()) == (403, NOT_REGISTERED)
    assert "+40700***009" in caplog.text
    assert "+40700000009" not in caplog.text  # the number, and here the token too


async def test_zero_grants(client, add_user):
    await add_user(DAS)  # a user whose grants were all revoked
    r = await client.get("/api/me", headers=signed_in(DAS))
    assert (r.status_code, r.json()) == (403, NOT_REGISTERED)


async def test_grants_in_role_order(client, add_user):
    await add_user("+40700000003", Role.medic, Role.das, name="Ana Pop")
    r = await client.get("/api/me", headers=signed_in("+40700000003"))
    assert r.status_code == 200
    assert r.json() == {
        "display_name": "Ana Pop",
        "phone_e164": "+40700000003",
        "grants": [
            {"role": "das", "senior_id": None},
            {"role": "medic", "senior_id": None},
        ],
    }


async def test_one_entry_per_caregiver_grant(client, db, add_user):
    user = await add_user("+40700000004")
    mother, father = uuid.uuid4(), uuid.uuid4()
    db.add_all(
        Grant(user_id=user.id, role=Role.caregiver, senior_id=s, relation="fiică")
        for s in (mother, father)
    )
    await db.commit()
    r = await client.get("/api/me", headers=signed_in("+40700000004"))
    grants = r.json()["grants"]
    assert [g["role"] for g in grants] == ["caregiver", "caregiver"]
    assert {g["senior_id"] for g in grants} == {str(mother), str(father)}


async def test_firebase_uid_written_kept_and_replaced(client, db, add_user, caplog):
    caplog.set_level(logging.WARNING, logger="sentinela.auth")
    await add_user(DAS, Role.das)
    stored = select(User.firebase_uid).where(User.phone_e164 == DAS)

    await client.get("/api/me", headers=signed_in(DAS))
    assert await db.scalar(stored) == f"uid-{DAS}"

    await client.get("/api/me", headers=signed_in(DAS))
    assert "firebase_uid changed" not in caplog.text

    await client.get("/api/me", headers=signed_in(f"{DAS}|new-uid"))
    assert await db.scalar(stored) == "new-uid"
    assert "firebase_uid changed" in caplog.text
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_me.py -q`
Expected: the `test_not_signed_in` cases fail with 404 instead of 401, and the rest fail with 404s, because `/api/me` does not exist yet.

- [ ] **Step 3: Implement the caller and the route**

Replace all of `backend/app/auth.py` with:

```python
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
    except (auth.InvalidIdTokenError, ValueError):
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
```

Replace all of `backend/app/main.py` with:

```python
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import Caller, current_caller, init_firebase
from app.db import engine
from app.settings import check_environment, check_firebase, get_settings

# Our own loggers at INFO, for refusals (auth-layer AL15); uvicorn sets up only its own.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("sentinela").setLevel(logging.INFO)

settings = get_settings()
check_environment(settings)
check_firebase(settings)
init_firebase(settings.firebase_service_account)

# Everything under /api, docs included, so the API and the dashboard can share one domain.
app = FastAPI(
    title="Sentinela",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
# Browser requests only from the dashboard's own address (01 §4, channel 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api")


@api.get("/health")
async def health() -> dict[str, str]:
    # Fails when the database is unreachable, so Railway holds back a broken deploy (06 §1).
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "env": settings.app_env}


class GrantView(BaseModel):
    role: str
    senior_id: uuid.UUID | None


class Me(BaseModel):
    """GET /me (auth-layer §3.3). Fields are only ever added: old apps read new servers."""

    display_name: str
    phone_e164: str
    grants: list[GrantView]


@api.get("/me")
async def me(caller: Annotated[Caller, Depends(current_caller)]) -> Me:
    return Me(
        display_name=caller.user.display_name,
        phone_e164=caller.user.phone_e164,
        grants=[GrantView(role=g.role, senior_id=g.senior_id) for g in caller.grants],
    )


# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest -q`
Expected: all pass. That's 34 from before plus 9 in `test_me.py` (4 + 1 + 1 + 1 + 1 + 1): 43.

- [ ] **Step 5: Bring the system spec in line**

In `docs/specs/sentinela/04-interfaces.md` §1, replace the row

```markdown
| My profile | `GET /me` | Any signed-in number | Display name and grants (role, and the senior for caregiver and senior grants). Whether a warning is active |
```

with

```markdown
| My profile | `GET /me` | Any number with a grant | Display name, phone number, and one entry per grant: role, and the senior for caregiver and senior grants; das first, then medic, caregiver, senior. Whether a warning is active, and the seniors' names, are added with the campaign and senior tables ([auth-layer.md](../auth-layer.md) §3.3) |
```

In `docs/specs/sentinela/01-architecture.md` §6, replace

```markdown
A grant creates the person's user row immediately, before they ever sign in. At first sign-in FastAPI attaches the Firebase account to that row.
```

with

```markdown
A grant creates the person's user row immediately, before they ever sign in. At first sign-in FastAPI attaches the Firebase account to that row. The phone number stays the key on every request: if a different Firebase account signs in with the number, FastAPI replaces the stored one and logs a warning ([auth-layer.md](../auth-layer.md) AL4).
```

replace

```markdown
| It has one grant | The app opens the screens for that role. The dashboard accepts DAS grants only |
| It has several grants (for example a caregiver who is also a medic, or a senior who uses a relative's phone) | The app asks which role to use, listing only the granted ones |
```

with

```markdown
| Its grants are all one role | The app opens the screens for that role. The dashboard accepts DAS grants only |
| Its grants span several roles (for example a caregiver who is also a medic, or a senior who uses a relative's phone) | The app asks which role to use, listing only the granted roles. Several grants of one role, such as a caregiver of both parents, are one role: its screens list every senior it covers |
```

and replace

```markdown
**One place enforces permissions: FastAPI.** Every endpoint checks the caller's grants and, where a senior is involved, that the grant covers that senior. The app's role screens are a convenience, not a protection.
```

with

```markdown
**One place enforces permissions: FastAPI.** Every endpoint checks the caller's grants and, where a senior is involved, that the grant covers that senior. The app's role screens are a convenience, not a protection. A caller may do what any of their grants allows; the role chosen in the app only picks screens. For one senior, the caller sees what the grants covering that senior allow in the table below. A medic covers a senior when they hold a medic grant and registered that senior. A senior outside the caller's reach answers "not found", as an id that does not exist does. A user holds at most one senior grant: when a couple shares one mobile, the second senior has no app role and still receives every call ([auth-layer.md](../auth-layer.md) AL2, AL7, AL8).
```

In `docs/specs/sentinela/02-use-cases.md` UC-02, replace

```markdown
5. One grant: the app opens that role's screens. Several: the app asks which role, listing only the granted ones.
```

with

```markdown
5. All grants one role: the app opens that role's screens. Several roles: the app asks which role, listing only the granted ones.
```

In `docs/specs/sentinela/05-data-model.md` §3, after the row

```markdown
| An incident is taken once | Taking updates the row only where `status` is still `open`; a second taker changes nothing and is told who has it |
```

add

```markdown
| At most one senior grant per user ([auth-layer.md](../auth-layer.md) AL7) | A unique index over `grant.user_id` limited to rows with role `senior`, added with the seniors migration |
```

and in §4 replace

```markdown
**The user row exists before sign-in.** Signing in is a lookup by phone number that fills `firebase_uid` the first time. A number with no row is refused and nothing is stored.
```

with

```markdown
**The user row exists before sign-in.** Signing in is a lookup by phone number that fills `firebase_uid` the first time. A number with no row is refused and nothing is stored. The phone number stays the lookup key; if a different Firebase account later signs in with the number, `firebase_uid` is replaced and a warning logged ([auth-layer.md](../auth-layer.md) AL4).
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth.py backend/app/main.py backend/tests/conftest.py backend/tests/test_me.py docs/specs/sentinela/04-interfaces.md docs/specs/sentinela/01-architecture.md docs/specs/sentinela/02-use-cases.md docs/specs/sentinela/05-data-model.md
git commit -m "backend: resolve the caller's grants and serve GET /api/me (auth-layer §3.1, §3.3)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `POST /api/staff`

**Files:**
- Create: `backend/app/staff.py`
- Create: `backend/tests/test_staff.py`
- Modify: `backend/app/main.py` (full replacement below)
- Modify (docs): `docs/specs/sentinela/04-interfaces.md` §2

**Interfaces:**
- Consumes:
  - From Task 1: `normalize`, `is_mobile`.
  - From Task 2: `User`, `Grant`, `Role`, `get_session`, `add_user`.
  - From Task 3: `refuse`.
  - From Task 4: `Caller`, `require_roles`, `client`.
- Produces:
  - `app.staff.grant_staff(session: AsyncSession, display_name: str, phone_e164: str, role: Role, practice: str | None, granted_by: uuid.UUID | None) -> User | None`. It returns `None` when the number already holds the role; nothing has changed then. Spec §6.1 calls this return value `created`; the user row is returned because the route answers with it.
  - The route `POST /api/staff`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_staff.py`:

```python
import asyncio

import pytest
from sqlalchemy import select

from app.models import Grant, Role, User

DAS = "+40700000001"
MEDIC = {
    "display_name": "Dr. Ion Pop",
    "phone": "0700 000 002",
    "role": "medic",
    "practice": "CMI Dr. Pop",
}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def das(add_user):
    return await add_user(DAS, Role.das, name="DAS Test")


async def post(client, body, token=DAS):
    return await client.post("/api/staff", json=body, headers=signed_in(token))


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
async def test_refusals(client, das, headers, status, reason):
    r = await client.post("/api/staff", json=MEDIC, headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
    if status == 401:
        assert r.headers["www-authenticate"] == "Bearer"


async def test_a_medic_cannot_grant(client, add_user):
    await add_user("+40700000003", Role.medic)
    r = await post(client, MEDIC, token="+40700000003")
    assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_allowed"}})


async def test_grant_a_new_medic(client, db, das):
    r = await post(client, MEDIC)
    assert r.status_code == 201
    assert r.json() == {
        "display_name": "Dr. Ion Pop",
        "phone_e164": "+40700000002",
        "role": "medic",
        "practice": "CMI Dr. Pop",
    }
    granted_by = await db.scalar(
        select(Grant.granted_by)
        .join(User, Grant.user_id == User.id)
        .where(User.phone_e164 == "+40700000002")
    )
    assert granted_by == das.id


async def test_the_new_medic_signs_in(client, das):
    # Typed as "0700 000 002", reported by Firebase as +40700000002: one user.
    await post(client, MEDIC)
    r = await client.get("/api/me", headers=signed_in("+40700000002"))
    assert r.status_code == 200
    assert r.json()["grants"] == [{"role": "medic", "senior_id": None}]


async def test_a_known_number_keeps_its_name(client, add_user, das):
    await add_user("+40700000002", Role.das, name="Ion Pop")
    r = await post(client, MEDIC)
    assert r.status_code == 201
    assert (r.json()["display_name"], r.json()["practice"]) == (
        "Ion Pop",
        "CMI Dr. Pop",
    )


async def test_a_repeated_grant_changes_nothing(client, db, das):
    await post(client, MEDIC)
    r = await post(client, {**MEDIC, "practice": "Alt cabinet"})
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "already_done"}})
    practice = select(User.practice).where(User.phone_e164 == "+40700000002")
    assert await db.scalar(practice) == "CMI Dr. Pop"


async def test_a_das_grant_keeps_the_practice(client, das):
    await post(client, MEDIC)
    r = await post(client, {**MEDIC, "role": "das", "practice": "Alt cabinet"})
    assert r.status_code == 201
    assert r.json()["practice"] == "CMI Dr. Pop"


@pytest.mark.parametrize(
    "change",
    [
        {"practice": None},  # a medic needs a practice
        {"practice": "   "},
        {"phone": "0256 123 456"},  # a landline cannot receive the sign-in SMS
        {"phone": "12345"},
        {"role": "caregiver"},  # medics grant caregivers, with a senior
        {"display_name": "   "},
    ],
)
async def test_invalid_bodies(client, das, change):
    r = await post(client, {**MEDIC, **change})
    assert r.status_code == 422


async def test_two_grants_at_once(client, das):
    first, second = await asyncio.gather(post(client, MEDIC), post(client, MEDIC))
    assert sorted([first.status_code, second.status_code]) == [201, 409]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_staff.py -q`
Expected: failures with 404 or 405 responses, because `/api/staff` does not exist yet.

- [ ] **Step 3: Implement the grant and the route**

`backend/app/staff.py`:

```python
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
```

Replace all of `backend/app/main.py` with:

```python
import logging
import uuid
from typing import Annotated, Literal, Self

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, StringConstraints, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller, current_caller, init_firebase, refuse, require_roles
from app.db import engine, get_session
from app.models import Role
from app.phones import is_mobile, normalize
from app.settings import check_environment, check_firebase, get_settings
from app.staff import grant_staff

# Our own loggers at INFO, for refusals (auth-layer AL15); uvicorn sets up only its own.
logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("sentinela").setLevel(logging.INFO)

settings = get_settings()
check_environment(settings)
check_firebase(settings)
init_firebase(settings.firebase_service_account)

# Everything under /api, docs included, so the API and the dashboard can share one domain.
app = FastAPI(
    title="Sentinela",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
# Browser requests only from the dashboard's own address (01 §4, channel 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.allowed_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api")


@api.get("/health")
async def health() -> dict[str, str]:
    # Fails when the database is unreachable, so Railway holds back a broken deploy (06 §1).
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "env": settings.app_env}


class GrantView(BaseModel):
    role: str
    senior_id: uuid.UUID | None


class Me(BaseModel):
    """GET /me (auth-layer §3.3). Fields are only ever added: old apps read new servers."""

    display_name: str
    phone_e164: str
    grants: list[GrantView]


@api.get("/me")
async def me(caller: Annotated[Caller, Depends(current_caller)]) -> Me:
    return Me(
        display_name=caller.user.display_name,
        phone_e164=caller.user.phone_e164,
        grants=[GrantView(role=g.role, senior_id=g.senior_id) for g in caller.grants],
    )


Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
Practice = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class StaffGrant(BaseModel):
    """POST /staff's body (auth-layer §3.4)."""

    display_name: Name
    phone: str
    role: Literal["das", "medic"]
    practice: Practice | None = None

    @field_validator("phone")
    @classmethod
    def mobile_e164(cls, raw: str) -> str:
        e164 = normalize(raw)
        if not is_mobile(e164):
            raise ValueError("staff sign in by SMS: the number must be a mobile")
        return e164

    @model_validator(mode="after")
    def medic_has_practice(self) -> Self:
        if self.role == "medic" and self.practice is None:
            raise ValueError("a medic needs a practice")
        return self


class StaffMember(BaseModel):
    display_name: str
    phone_e164: str
    role: str
    practice: str | None


@api.post("/staff", status_code=201)
async def grant_staff_member(
    body: StaffGrant,
    caller: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StaffMember:
    user = await grant_staff(
        session,
        body.display_name,
        body.phone,
        Role(body.role),
        body.practice,
        caller.user.id,
    )
    if user is None:
        raise refuse(409, "already_done")
    return StaffMember(
        display_name=user.display_name,
        phone_e164=user.phone_e164,
        role=body.role,
        practice=user.practice,
    )


# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)
```

- [ ] **Step 4: Run them to see them pass**

Run: `uv run pytest -q`
Expected: all pass. That's 43 from before plus 17 in `test_staff.py` (4 + 1 + 1 + 1 + 1 + 1 + 1 + 6 + 1): 60.

- [ ] **Step 5: Bring the contract in line**

In `docs/specs/sentinela/04-interfaces.md` §2, replace the row

```markdown
| Grant staff | `POST /staff` | DAS | Creates the user row and a `medic` or `das` grant for the number | The number already has that grant |
```

with

```markdown
| Grant staff | `POST /staff` | DAS | Display name, phone number (a mobile: staff sign in by SMS), role `medic` or `das`, and the practice for a medic. Creates the user row if the number has none, keeping an existing name, and the grant ([auth-layer.md](../auth-layer.md) §3.4) | The number already has that grant (`already_done`); nothing changes |
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/staff.py backend/app/main.py backend/tests/test_staff.py docs/specs/sentinela/04-interfaces.md
git commit -m "backend: let DAS grant medics and DAS through POST /api/staff (UC-14, auth-layer §3.4)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The setup script and the developer token script

**Files:**
- Create: `backend/scripts/grant_das.py`
- Create: `backend/scripts/dev_token.py`
- Create: `backend/tests/test_scripts.py`
- Modify (docs): `backend/README.md` (a new section), `backend/AGENTS.md` (the layout)

**Interfaces:**
- Consumes:
  - From Task 1: `normalize`, `is_mobile`.
  - From Task 2: `Session`, `Role`, and the `db` fixture.
  - From Task 3: `init_firebase`.
  - From Task 5: `grant_staff`.
- Produces:
  - `scripts.grant_das.grant_das(display_name: str, phone: str) -> str`, which returns `"granted"`, `"already granted"` or `"invalid"`.
  - Two command-line tools, `grant_das.py` and `dev_token.py`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_scripts.py`:

```python
from scripts.grant_das import grant_das


async def test_grant_das_twice(db):
    assert await grant_das("Ana Pop", "0700 000 001") == "granted"
    assert await grant_das("Ana Pop", "+40700000001") == "already granted"


async def test_grant_das_refuses_a_landline(db):
    assert await grant_das("Ana Pop", "0256 123 456") == "invalid"
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_scripts.py -q`
Expected: a collection error, `ModuleNotFoundError: No module named 'scripts'`.

- [ ] **Step 3: Implement both scripts**

`backend/scripts/grant_das.py`:

```python
"""Grant the DAS role to a phone number: the setup script of G6.

Run it inside the api container (locally `docker compose exec api`, on Railway
`railway ssh -s api -e staging`):

    python scripts/grant_das.py "Ana Pop" 0722123456
"""

import asyncio
import sys
from pathlib import Path

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Session
from app.models import Role
from app.phones import is_mobile, normalize
from app.staff import grant_staff


async def grant_das(display_name: str, phone: str) -> str:
    """Returns granted, already granted, or invalid for a number that cannot sign in."""
    try:
        e164 = normalize(phone)
    except ValueError:
        return "invalid"
    if not is_mobile(e164):
        return "invalid"
    async with Session() as session:
        user = await grant_staff(
            session, display_name.strip(), e164, Role.das, None, None
        )
    return "granted" if user else "already granted"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    result = asyncio.run(grant_das(sys.argv[1], sys.argv[2]))
    print(result)
    return 2 if result == "invalid" else 0


if __name__ == "__main__":
    sys.exit(main())
```

`backend/scripts/dev_token.py`:

```python
"""Print a real Firebase identity token for a phone number, to call the API by hand.

Needs the laptop key in backend/.env as FIREBASE_SERVICE_ACCOUNT (auth-layer AL10).
From backend/:

    uv run python scripts/dev_token.py +40700000001

Paste the token into Authorize at /api/docs, or use it with curl. It lasts an hour.
"""

import json
import sys
import urllib.request
from pathlib import Path

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firebase_admin import auth

from app.auth import init_firebase
from app.phones import normalize
from app.settings import get_settings

# Public: the dashboard ships it in every browser bundle (.railway/railway.ts).
WEB_API_KEY = "AIzaSyBWFvTyqk904SsoT_uFXIzXgyHBBxhz5m0"
EXCHANGE = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
    f"?key={WEB_API_KEY}"
)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    service_account = get_settings().firebase_service_account
    if not service_account:
        print("Set FIREBASE_SERVICE_ACCOUNT in backend/.env first.", file=sys.stderr)
        return 2
    init_firebase(service_account)
    phone = normalize(sys.argv[1])
    try:
        uid = auth.get_user_by_phone_number(phone).uid
    except auth.UserNotFoundError:
        uid = auth.create_user(phone_number=phone).uid
    custom = auth.create_custom_token(uid).decode()
    request = urllib.request.Request(
        EXCHANGE,
        data=json.dumps({"token": custom, "returnSecureToken": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        print(json.load(response)["idToken"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`dev_token.py` needs the laptop key and the network, so Task 7 checks it by hand.

- [ ] **Step 4: Run it to see it pass**

Run: `uv run pytest -q`
Expected: `62 passed`. Then `uv run ruff check . && uv run ruff format --check .`; expected: `All checks passed!` and `… files already formatted`.

- [ ] **Step 5: Document signing in by hand and the new layout**

In `backend/README.md`, insert this section right before `## Migrations`:

````markdown
## Sign in by hand

Every client signs in with a phone number ([auth-layer.md](../docs/specs/auth-layer.md)). With the laptop key in `.env` as `FIREBASE_SERVICE_ACCOUNT`, these Firebase test numbers need no SMS:

| Number | Code | Granted as |
|---|---|---|
| `+40700000001` | `111111` | DAS |
| `+40700000002` | `222222` | medic |
| `+40700000003` | `333333` | DAS and medic |
| `+40700000009` | `999999` | nothing |

Grants live in each environment's database. Locally, grant DAS with the setup script (on Railway, run the same inside `railway ssh -s api -e staging`):

```bash
docker compose exec api python scripts/grant_das.py "DAS Test" +40700000001
```

A real token for any number, valid for an hour. Paste it into Authorize at http://localhost:8000/api/docs, or use it with curl:

```bash
TOKEN=$(uv run python scripts/dev_token.py +40700000001)
```

```bash
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/me
```

A DAS grants medics through the API:

```bash
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"display_name": "Medic Test", "phone": "+40700000002", "role": "medic", "practice": "CMI Test"}' localhost:8000/api/staff
```

````

In `backend/AGENTS.md`, replace the layout block

```
backend/
├── app/
│   ├── main.py        FastAPI app; every route on the /api router, docs at /api/docs
│   ├── settings.py    pydantic-settings from env / .env; check_environment() guard
│   └── db.py          async engine (asyncpg), declarative Base for models
├── alembic/
```

with

```
backend/
├── app/
│   ├── main.py        FastAPI app; every route on the /api router, docs at /api/docs
│   ├── settings.py    pydantic-settings from env / .env; check_environment(), check_firebase()
│   ├── db.py          async engine (asyncpg), Session and get_session, declarative Base
│   ├── models.py      tables (05), only those the built features use
│   ├── auth.py        Firebase token check, the caller and their grants, refusals (auth-layer §3)
│   ├── staff.py       granting staff roles, for POST /staff and grant_das.py
│   └── phones.py      phone numbers to E.164
├── scripts/
│   ├── grant_das.py   the setup script (G6), run inside the api container
│   └── dev_token.py   a real sign-in token for a phone number, for curl and Swagger
├── alembic/
```

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/grant_das.py backend/scripts/dev_token.py backend/tests/test_scripts.py backend/README.md backend/AGENTS.md
git commit -m "backend: add the grant_das and dev_token scripts (G6, auth-layer AL10)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Final verification and the real-token check

**Files:** none changed, unless a check fails.

**Interfaces:**
- Consumes: everything above.
- Produces: a report covering steps 1 to 4.

- [ ] **Step 1: Run the whole suite and lint, as CI does**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
Expected: `62 passed`, `All checks passed!`, `… files already formatted`.

- [ ] **Step 2: Check the running API and Swagger's Authorize button**

Run (from the repository root): `docker compose up -d --build api`. It rebuilds the image for the new dependencies, and its start command applies the migration to the local `sentinela` database.

Run: `curl -s localhost:8000/api/health`
Expected: `{"status":"ok","env":"local"}`

Run: `curl -s localhost:8000/api/openapi.json | python3 -c "import json,sys; print(json.load(sys.stdin)['components']['securitySchemes'])"`
Expected: `{'HTTPBearer': {'type': 'http', 'scheme': 'bearer'}}`

Run: `curl -s -i localhost:8000/api/me | head -1`
Expected: `HTTP/1.1 401 Unauthorized`

- [ ] **Step 3: The real-token check (spec §6.3 step 10)**

This needs the laptop key in `backend/.env` as `FIREBASE_SERVICE_ACCOUNT`. If it is not there, report that this step is waiting on the key, and stop here.

1. Restart the API so it reads the key: `docker compose up -d --force-recreate api`.
2. `docker compose exec api python scripts/grant_das.py "DAS Test" +40700000001`. Expected: `granted` (or `already granted`).
3. From `backend/`, run `TOKEN=$(uv run python scripts/dev_token.py +40700000001)`.
4. Run `uv run python -c "import base64,json,sys; p=sys.argv[1].split('.')[1]; print(json.dumps(json.loads(base64.urlsafe_b64decode(p + '=' * (-len(p) % 4))), indent=1))" "$TOKEN"`. Expected: the claims include `"phone_number": "+40700000001"`.
5. Run `curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/me`. Expected: `{"display_name":"DAS Test","phone_e164":"+40700000001","grants":[{"role":"das","senior_id":null}]}`.
6. Run `curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"display_name": "Medic Test", "phone": "+40700000002", "role": "medic", "practice": "CMI Test"}' localhost:8000/api/staff`. Expected: a 201 body with `"role":"medic"`.

**If step 4's claims have no `phone_number`, or step 5 answers 401,** stop. Report the decoded claims (they hold no secret) and leave the verifier unchanged. This is the open fact in spec §11.

- [ ] **Step 4: Report and hand over**

Report:
- the output of steps 1 and 2;
- the result of step 3, including the decoded claims;
- the output of `railway config plan` if you ran it in Task 3.

Then ask the person whether to push `auth-layer` and open the PR. CI runs on pull requests, and `backend.yml` must be green there before the PR merges. Before it merges, the person sets `FIREBASE_SERVICE_ACCOUNT` on staging (spec §9 step 2).
