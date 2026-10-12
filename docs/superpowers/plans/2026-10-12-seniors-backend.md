# Seniors and enrollment, backend slice: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A medic registers a senior with caregivers through the API, DAS accepts the senior, and every number reaches only the seniors its grants cover. This is slice 1 of the spec. It closes #16 and #18 and builds the backend half of #17.

**Architecture:**
- `reaches(caller, *roles)` in `app/reach.py` turns auth-layer §3.6 into one SQL condition. Every list and every single lookup uses it, so the two cannot disagree.
- `app/seniors.py` holds the senior, caregiver and enrollment routes on its own router, which `main.py` includes into `api`.
- `user_for_number()` in `app/grants.py` makes the user row behind a grant. Staff, senior and caregiver grants share it.
- A state transition is one `UPDATE … WHERE state = <expected>`, so of two submits or two accepts at once, one wins.
- A refused command raises before it commits. The request's session rolls back when it closes, so nothing is half-written.
- No table changes. The `seniors` table and both of its constraints shipped with migration `741f75a7dbe1`.

**Tech stack:** Python 3.14, FastAPI, SQLAlchemy 2 (async, asyncpg), Postgres 18, pydantic 2, pytest with pytest-asyncio and httpx, uv, ruff. No new dependency.

**Spec:** [docs/specs/seniors-and-enrollment.md](../../specs/seniors-and-enrollment.md), sections 1 to 6. Read §1 to §5 before Task 1; §6 is the backend brief this plan implements.

**This code was run before the plan was written.** Tasks 1 to 7 were replayed in order on a fresh copy of `backend/` against Compose's Postgres 18.6:
- At every task the new tests failed before the code and passed after it.
- The whole suite passed after every task: 243, 243, 278, 317, 339, 374 and 382 tests.
- `ruff check` and `ruff format --check` (the repository's defaults) were clean after every task.
- `alembic check` reported no new upgrade operations.
- Each of Task 8's 27 doc edits was checked to find its text exactly once.

Task 9's commands were run against the same API with the tests' stand-in verifier, where the token is the phone number: every line of the story showed the status it wants, on a first and on a second run. They were **not** run with real Firebase tokens, because that needs a test number a person has to add first.

If a step's expected output differs, look for a difference in the environment or a block that was not copied exactly before changing the code.

## Global Constraints

- Work on the branch `auth-layer`, from the repository root. Every `uv` command runs from `backend/`.
- **Database:** Compose's Postgres must be running (`docker compose up -d db`, which needs Docker Desktop started), and `sentinela_test` must exist. On a volume created before Compose's init script, create it once with `docker compose exec db createdb -U sentinela sentinela_test`. Tests never use `sentinela`.
- **Commits run the hooks:** lefthook's pre-commit runs `ruff check --fix`, `ruff format` and `uv run pytest -q` when backend `.py` files are staged, so the database must be up when you commit. Never pass `--no-verify`. Every block in this plan is already formatted; if the hook changes a staged file, read `git diff` and report it, because it means a block was not copied exactly.
- **No migration.** Do not run `alembic revision`. Nothing under `backend/alembic/` changes.
- **Refusal body:** exactly `{"detail": {"reason": "<reason>"}}`, made with `refuse()` from `app/auth.py`. The reasons these endpoints use are `not_signed_in` (401), `not_registered` and `not_allowed` (403), `not_found` (404), `wrong_state`, `already_done` and `phone_taken` (409), and `missing_fields` (422, with a `fields` list).
- **Check order** (spec §3.1): identity, role, body, reach, state. FastAPI gives the first three in that order by itself, because dependencies run before the body is validated.
- **A refused command changes nothing.** Raise before `session.commit()`.
- **Phone numbers:** every number passes through `normalize()` from `app/phones.py` and is stored as E.164.
- **Logs** carry the reason and the user id, never a phone number or a token (auth-layer AL15).
- **Comments cite the spec by ID.** This spec is cited as `seniors SE5` or `seniors §3.1`; the others as before (`auth-layer §3.6`, `04 §1`, `UC-01`).
- **API changes only add** (ADR-001 §2.3). `/me` gains two fields; nothing is renamed or removed.
- **Every route** is on the `api` router, or on a router included into it before `app.include_router(api)` at the bottom of `main.py`.
- **Copy each code block exactly.** Later tasks append to files that earlier tasks made, and say "find this text". A block retyped from memory will not match.
- **Cloud environments are off limits:** no deploys and no Railway commands. Push and open a PR only when the person asks.
- **Commit messages** start with `backend:` or `docs:` and end with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

Inputs the spec implies but does not spell out, each pinned by a test in the task that owns the code:

1. **An optional field sent as spaces**, which is what a form sends for an input the medic tabbed through, must be stored as null. The first version of this code answered it with a 500. Pinned by `test_optional_fields_are_trimmed_and_a_blank_is_null` and the `"  "` case of `test_past_draft_the_address_stays` (Task 4).
2. **One number typed two ways**, `0700 000 005` when registering and `+40700000005` when editing, is the same number. The edit must not delete and remake the senior's grant. Pinned by `test_put_with_the_same_number_keeps_the_grant` (Task 4).
3. **A refused save** must leave nothing half-written: no senior row after `phone_taken` on create, and the old name, number and grant after `phone_taken` on edit. Pinned by `test_another_seniors_mobile_is_taken` and `test_put_to_a_taken_number_changes_nothing` (Task 4).
4. **Removing a caregiver who holds other grants**, as a medic, as another senior's caregiver, or as the senior herself on a shared phone, removes only that one grant. Pinned by `test_removing_keeps_their_other_grants` and `test_the_seniors_own_mobile_can_care` (Task 5).
5. **A state name this copy does not know**, written by a newer copy during a deploy, must be served as a string and count as "not draft" for DAS. Pinned by `test_a_state_this_copy_does_not_know_is_served` (Task 3).

## How the tasks map to the spec

| Spec §6.3 step | Task |
|---|---|
| 1 `app/grants.py` | 1 |
| 7 `/me` additions | 2, moved early because the tests of Tasks 4 and 5 read the new fields |
| 2 `app/reach.py`, 3 the two reads | 3 |
| 4 `POST` and `PUT /seniors` | 4 |
| 5 caregivers | 5 |
| 6 submit, accept, `GET /enrollments` | 6 |
| 8 `GET /staff` | 7 |
| 9 docs (§6.6) | 8 |
| 10 real-token check | 9 |

`app/seniors.py` is created in Task 3 and grows by one section in each of Tasks 4, 5 and 6. Each section is appended to the end of the file.

---

### Task 1: The user row behind a grant

**Files:**
- Create: `backend/app/grants.py`
- Create: `backend/tests/test_grants.py`
- Modify: `backend/app/staff.py`

**Interfaces:**
- Consumes: `User` from `app/models.py`; the fixtures `db` and `add_user` from `tests/conftest.py`.
- Produces: `async def user_for_number(session: AsyncSession, phone_e164: str, display_name: str) -> User`. It makes the row if the number has none, never renames an existing user, and does not commit. Tasks 4 and 5 call it.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_grants.py`:

```python
"""The user row behind a grant (app/grants.py)."""

from sqlalchemy import func, select

from app.grants import user_for_number
from app.models import User

PHONE = "+40700000004"


async def test_a_new_number_gets_a_user(db):
    user = await user_for_number(db, PHONE, "Ioana Pop")
    await db.commit()
    assert (user.phone_e164, user.display_name) == (PHONE, "Ioana Pop")
    assert user.id is not None


async def test_a_known_number_keeps_its_user_and_name(db, add_user):
    known = await add_user(PHONE, name="Dr. Ioana Pop")
    user = await user_for_number(db, PHONE, "Ioana")
    await db.commit()
    assert (user.id, user.display_name) == (known.id, "Dr. Ioana Pop")
    assert await db.scalar(select(func.count()).select_from(User)) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_grants.py -q`
Expected: `1 error`, from `ModuleNotFoundError: No module named 'app.grants'`.

- [ ] **Step 3: Write `app/grants.py`**

Create `backend/app/grants.py`:

```python
"""The user row behind a grant (01 §6): made when a number is first granted anything."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def user_for_number(
    session: AsyncSession, phone_e164: str, display_name: str
) -> User:
    """The number's user, made with `display_name` if the number has none.

    A user that exists keeps their name (auth-layer §3.4). The insert is ON CONFLICT
    DO NOTHING, so two grants of one new number at the same moment make one row.
    """
    await session.execute(
        insert(User)
        .values(phone_e164=phone_e164, display_name=display_name)
        .on_conflict_do_nothing(index_elements=[User.phone_e164])
    )
    found = await session.scalars(select(User).where(User.phone_e164 == phone_e164))
    return found.one()
```

- [ ] **Step 4: Use it in `app/staff.py`**

In `backend/app/staff.py`, change the imports. `select` is no longer used here until Task 7 brings it back.

Find:

```python
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Grant, Role, User
```

Replace it with:

```python
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.grants import user_for_number
from app.models import Grant, Role, User
```

Then, in `grant_staff`:

Find:

```python
    await session.execute(
        insert(User)
        .values(phone_e164=phone_e164, display_name=display_name)
        .on_conflict_do_nothing(index_elements=[User.phone_e164])
    )
    user = await session.scalar(select(User).where(User.phone_e164 == phone_e164))
```

Replace it with:

```python
    user = await user_for_number(session, phone_e164, display_name)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_grants.py tests/test_staff.py tests/test_scripts.py -q`
Expected: `29 passed`. `test_staff.py` and `test_scripts.py` pass unchanged, which shows `grant_staff` behaves as before.

- [ ] **Step 6: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: `All checks passed!` and no file to reformat.

- [ ] **Step 7: Commit**

```bash
git add backend/app/grants.py backend/app/staff.py backend/tests/test_grants.py
git commit -F - <<'EOF'
backend: share the user row behind a grant (app/grants.py)

Staff, senior and caregiver grants all start by making the number's user
row if it has none. grant_staff() now calls user_for_number().

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: `/me` names the senior and the relation

**Files:**
- Modify: `backend/tests/test_me.py`
- Modify: `backend/tests/test_staff.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `Caller.grants`, a list of `Grant` rows, each with `role`, `senior_id` and `relation`.
- Produces: every grant in `GET /api/me` carries two more keys, `senior_form_of_address` and `relation`, both `null` for a `das` or `medic` grant (spec §3.3). The tests of Tasks 4 and 5, and the clients, read them.

- [ ] **Step 1: Change the tests to the new shape**

In `backend/tests/test_me.py`, add a constant for what a staff grant carries:

Find:

```python
NOT_REGISTERED = {"detail": {"reason": "not_registered"}}
```

Replace it with:

```python
NOT_REGISTERED = {"detail": {"reason": "not_registered"}}
# What a das or medic grant carries besides its role (seniors §3.3).
NO_SENIOR = {"senior_id": None, "senior_form_of_address": None, "relation": None}
```

In `test_grants_in_role_order`:

Find:

```python
            {"role": "das", "senior_id": None},
            {"role": "medic", "senior_id": None},
```

Replace it with:

```python
            {"role": "das", **NO_SENIOR},
            {"role": "medic", **NO_SENIOR},
```

In `test_one_entry_per_caregiver_grant`:

Find:

```python
    assert {g["senior_id"] for g in grants} == {str(mother), str(father)}
```

Replace it with:

```python
    assert {g["senior_id"] for g in grants} == {str(mother), str(father)}
    # Each names its senior and the relation (seniors §3.3).
    assert [g["senior_form_of_address"] for g in grants] == ["doamna Maria"] * 2
    assert [g["relation"] for g in grants] == ["fiică", "fiică"]
```

In `backend/tests/test_staff.py`, in `test_the_new_medic_signs_in`:

Find:

```python
    assert r.json()["grants"] == [{"role": "medic", "senior_id": None}]
```

Replace it with:

```python
    assert r.json()["grants"] == [
        {
            "role": "medic",
            "senior_id": None,
            "senior_form_of_address": None,
            "relation": None,
        }
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_me.py tests/test_staff.py -q`
Expected: `3 failed, 26 passed`. The three are `test_grants_in_role_order`, `test_one_entry_per_caregiver_grant` (`KeyError: 'senior_form_of_address'`) and `test_the_new_medic_signs_in`.

- [ ] **Step 3: Add the two fields**

In `backend/app/main.py`:

Find:

```python
class GrantView(BaseModel):
    role: str
    senior_id: uuid.UUID | None
```

Replace it with:

```python
class GrantView(BaseModel):
    role: str
    senior_id: uuid.UUID | None
    # Added with the seniors work (seniors §3.3); null where they do not apply.
    senior_form_of_address: str | None = None
    relation: str | None = None
```

Then the handler. `Senior`, `select`, `AsyncSession` and `get_session` are already imported in `main.py`.

Find:

```python
@api.get("/me")
async def me(caller: Annotated[Caller, Depends(current_caller)]) -> Me:
    return Me(
        display_name=caller.user.display_name,
        phone_e164=caller.user.phone_e164,
        grants=[GrantView(role=g.role, senior_id=g.senior_id) for g in caller.grants],
    )
```

Replace it with:

```python
@api.get("/me")
async def me(
    caller: Annotated[Caller, Depends(current_caller)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Me:
    named = [g.senior_id for g in caller.grants if g.senior_id is not None]
    # Only a caregiver or a senior pays for this second query.
    addressed: dict[uuid.UUID, str] = {}
    if named:
        rows = await session.execute(
            select(Senior.id, Senior.form_of_address).where(Senior.id.in_(named))
        )
        addressed = {senior_id: address for senior_id, address in rows}
    return Me(
        display_name=caller.user.display_name,
        phone_e164=caller.user.phone_e164,
        grants=[
            GrantView(
                role=g.role,
                senior_id=g.senior_id,
                senior_form_of_address=addressed.get(g.senior_id),
                relation=g.relation,
            )
            for g in caller.grants
        ],
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_me.py tests/test_staff.py -q`
Expected: `29 passed`.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_me.py backend/tests/test_staff.py
git commit -F - <<'EOF'
backend: name the senior and the relation in GET /me (seniors §3.3)

Each grant gains senior_form_of_address and relation, null where they do
not apply. Optional additions: old clients ignore them (ADR-001 §2.3).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: The reach rule and the two reads

**Files:**
- Create: `backend/app/reach.py`
- Create: `backend/app/seniors.py`
- Create: `backend/tests/test_reach.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `Caller` (with `user`, `grants` and `roles`) and `refuse` from `app/auth.py`; `Senior`, `EnrollmentState`, `Role`, `Grant`, `User` from `app/models.py`.
- Produces, in `app/reach.py`:
  - `def reaches(caller: Caller, *roles: Role) -> ColumnElement[bool]`
  - `async def reachable_senior(session: AsyncSession, caller: Caller, senior_id: uuid.UUID, *roles: Role, lock: bool = False) -> Senior`, which raises 404 `not_found`.
- Produces, in `app/seniors.py`:
  - `router`, an `APIRouter`.
  - The parameter types `AnyCaller`, `AsMedic`, `AsDas`, `AsMedicOrDas` and `Db`. All five are defined now; Tasks 4 to 6 use the last three callers.
  - The models `SeniorRow`, `MedicView`, `CaregiverView`, `SeniorPage`.
  - `async def page(session: AsyncSession, senior: Senior) -> SeniorPage`.
  - `GET /api/seniors` and `GET /api/seniors/{senior_id}`.
- Produces, in `tests/conftest.py`: `add_senior(phone, name="Maria Pop", medic=None, **columns)`.

- [ ] **Step 1: Let `add_senior` name the medic and other columns**

In `backend/tests/conftest.py`. `Any` and `User` are already imported there.

Find:

```python
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
```

Replace it with:

```python
    """add_senior("+40700000101"): a draft senior, which caregiver and senior grants
    can name now that grants.senior_id has its key (AL6). Registered by `medic`, or by
    a fresh one. Other columns go by name: enrollment_state=..., street=...
    """

    async def add(
        phone: str, name: str = "Maria Pop", medic: User | None = None, **columns: Any
    ) -> Senior:
        if medic is None:
            medic = await add_user(f"+4079{phone[-7:]}", Role.medic, name="Medic")
        senior = Senior(
            medic_id=medic.id,
            full_name=name,
            form_of_address="doamna Maria",
            phone_e164=phone,
            phone_is_landline=False,
            **columns,
        )
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_reach.py`:

```python
"""Who reaches which senior (seniors §3.1, auth-layer §3.6), read through
GET /seniors and GET /seniors/{id}."""

import logging
import uuid

import pytest
from sqlalchemy import delete, select, text

from app.models import EnrollmentState, Grant, Role, User

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
SENIOR_DRAFT = "+40700000005"
SENIOR_SUBMITTED = "+40700000006"
OTHER_CAREGIVER = "+40700000007"
EX_MEDIC = "+40700000008"
NOT_FOUND = {"detail": {"reason": "not_found"}}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def seniors(db, add_user, add_senior):
    """Four seniors, named for what they are, and everyone who may look.
    Returns their ids by name."""
    medic = await add_user(MEDIC, Role.medic)
    other_medic = await add_user(OTHER_MEDIC, Role.medic)
    ex_medic = await add_user(EX_MEDIC, Role.medic)
    await add_user(DAS, Role.das)
    submitted = EnrollmentState.submitted
    draft = await add_senior("+40256000001", "draft", medic)
    sent = await add_senior(
        "+40256000002", "submitted", medic, enrollment_state=submitted
    )
    other = await add_senior(
        "+40256000003", "other", other_medic, enrollment_state=submitted
    )
    orphan = await add_senior("+40256000004", "orphan", ex_medic)
    caregiver = await add_user(CAREGIVER)
    other_caregiver = await add_user(OTHER_CAREGIVER)
    senior_draft = await add_user(SENIOR_DRAFT)
    senior_submitted = await add_user(SENIOR_SUBMITTED)
    db.add_all(
        [
            Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=draft.id),
            Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=sent.id),
            Grant(user_id=other_caregiver.id, role=Role.caregiver, senior_id=other.id),
            Grant(user_id=senior_draft.id, role=Role.senior, senior_id=draft.id),
            Grant(user_id=senior_submitted.id, role=Role.senior, senior_id=sent.id),
            # Once a medic, now only a caregiver; the orphan's medic_id is still theirs.
            Grant(user_id=ex_medic.id, role=Role.caregiver, senior_id=other.id),
        ]
    )
    await db.execute(
        delete(Grant).where(Grant.user_id == ex_medic.id, Grant.role == Role.medic)
    )
    await db.commit()
    return {s.full_name: s.id for s in (draft, sent, other, orphan)}


REACH = [
    (MEDIC, {"draft", "submitted"}),
    (OTHER_MEDIC, {"other"}),
    (EX_MEDIC, {"other"}),  # as a caregiver; not the orphan they registered
    (CAREGIVER, {"draft", "submitted"}),
    (SENIOR_DRAFT, {"draft"}),
    (SENIOR_SUBMITTED, {"submitted"}),
    (OTHER_CAREGIVER, {"other"}),
    (DAS, {"submitted", "other"}),  # never a draft
]


@pytest.mark.parametrize(("token", "reached"), REACH)
async def test_the_list_is_what_the_caller_reaches(client, seniors, token, reached):
    r = await client.get("/api/seniors", headers=signed_in(token))
    assert r.status_code == 200
    assert {s["full_name"] for s in r.json()} == reached


@pytest.mark.parametrize(("token", "reached"), REACH)
async def test_a_senior_outside_reach_is_not_found(client, seniors, token, reached):
    for name, senior_id in seniors.items():
        r = await client.get(f"/api/seniors/{senior_id}", headers=signed_in(token))
        if name in reached:
            assert (r.status_code, r.json()["full_name"]) == (200, name)
        else:
            assert (r.status_code, r.json()) == (404, NOT_FOUND)


async def test_an_id_that_does_not_exist_is_not_found(client, seniors):
    r = await client.get(f"/api/seniors/{uuid.uuid4()}", headers=signed_in(DAS))
    assert (r.status_code, r.json()) == (404, NOT_FOUND)


async def test_newest_first(client, seniors):
    r = await client.get("/api/seniors", headers=signed_in(MEDIC))
    assert [s["full_name"] for s in r.json()] == ["submitted", "draft"]


async def test_one_row(client, seniors):
    r = await client.get("/api/seniors", headers=signed_in(SENIOR_DRAFT))
    assert r.json() == [
        {
            "id": str(seniors["draft"]),
            "full_name": "draft",
            "form_of_address": "doamna Maria",
            "phone_e164": "+40256000001",
            "phone_is_landline": False,
            "enrollment_state": "draft",
        }
    ]


@pytest.mark.parametrize(
    ("role", "reached"),
    [
        (None, {"draft", "submitted", "other"}),  # the union (AL2)
        ("medic", {"draft", "submitted"}),
        ("caregiver", {"other"}),
        ("senior", set()),
        ("das", set()),  # a role they do not hold: an empty list, not a refusal
    ],
)
async def test_role_narrows_the_list(client, db, seniors, role, reached):
    # The medic is also the caregiver of another medic's senior.
    medic_id = await db.scalar(select(User.id).where(User.phone_e164 == MEDIC))
    db.add(Grant(user_id=medic_id, role=Role.caregiver, senior_id=seniors["other"]))
    await db.commit()
    r = await client.get(
        "/api/seniors", params={"role": role} if role else {}, headers=signed_in(MEDIC)
    )
    assert r.status_code == 200
    assert {s["full_name"] for s in r.json()} == reached


async def test_an_unknown_role_is_a_422(client, seniors):
    r = await client.get("/api/seniors?role=nurse", headers=signed_in(MEDIC))
    assert r.status_code == 422


async def test_a_state_this_copy_does_not_know_is_served(client, db, seniors):
    # Written by a newer copy during a deploy (ADR-001 §2.3). It is not draft, so DAS
    # reaches it, and it is served as the plain string it is.
    await db.execute(
        text("UPDATE seniors SET enrollment_state = 'paused' WHERE id = :id"),
        {"id": seniors["draft"]},
    )
    await db.commit()
    for token in (DAS, MEDIC):
        r = await client.get(
            f"/api/seniors/{seniors['draft']}", headers=signed_in(token)
        )
        assert (r.status_code, r.json()["enrollment_state"]) == (200, "paused")
    listed = await client.get("/api/seniors", headers=signed_in(DAS))
    assert "paused" in [s["enrollment_state"] for s in listed.json()]


async def test_a_refusal_is_logged_without_a_number(client, seniors, caplog):
    caplog.set_level(logging.INFO, logger="sentinela")
    await client.get(f"/api/seniors/{seniors['draft']}", headers=signed_in(DAS))
    assert "refused not_found: user " in caplog.text
    assert f"senior {seniors['draft']}" in caplog.text
    assert DAS not in caplog.text  # the user id, never the number (auth-layer AL15)


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
@pytest.mark.parametrize("path", ["/api/seniors", "/api/seniors/{id}"])
async def test_refusals(client, seniors, path, headers, status, reason):
    r = await client.get(path.format(id=seniors["submitted"]), headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_reach.py -q`
Expected: `35 failed`. Every request answers 404 `Not Found`, because the routes do not exist yet.

- [ ] **Step 4: Write `app/reach.py`**

Create `backend/app/reach.py`:

```python
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
    state and then writes.
    """
    query = select(Senior).where(Senior.id == senior_id, reaches(caller, *roles))
    if lock:
        query = query.with_for_update()
    senior = await session.scalar(query)
    if senior is None:
        log.info("refused not_found: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(404, "not_found")
    return senior
```

- [ ] **Step 5: Write `app/seniors.py` with the two reads**

Create `backend/app/seniors.py`:

```python
"""Seniors, their caregivers and enrollment (UC-01, UC-04 step 1): the reads and
commands of seniors §3.3 and §3.4 (docs/specs/seniors-and-enrollment.md).

Fields are only ever added (ADR-001 §2.3). The code, calls, consent, watch and home
node join these reads with their own features.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller, current_caller, require_roles
from app.db import get_session
from app.models import Grant, Role, Senior, User
from app.reach import reachable_senior, reaches

log = logging.getLogger("sentinela.seniors")
router = APIRouter()

# Who may call, as route parameters. A caller without the role gets 403 not_allowed.
AnyCaller = Annotated[Caller, Depends(current_caller)]
AsMedic = Annotated[Caller, Depends(require_roles(Role.medic))]
AsDas = Annotated[Caller, Depends(require_roles(Role.das))]
# The registration and the caregivers may be changed by either (seniors SE9).
AsMedicOrDas = Annotated[Caller, Depends(require_roles(Role.medic, Role.das))]
Db = Annotated[AsyncSession, Depends(get_session)]


class SeniorRow(BaseModel):
    """One row of GET /seniors and GET /enrollments (seniors §3.3)."""

    id: uuid.UUID
    full_name: str
    form_of_address: str
    phone_e164: str
    phone_is_landline: bool
    # A string, not the enum: a state a newer copy added must still be served.
    enrollment_state: str


class MedicView(BaseModel):
    display_name: str
    practice: str | None


class CaregiverView(BaseModel):
    user_id: uuid.UUID
    display_name: str
    relation: str | None
    phone_e164: str


class SeniorPage(SeniorRow):
    """GET /seniors/{id}, and the answer of every senior command: one shape for every
    role (seniors SE7)."""

    street: str | None
    street_number: str | None
    block: str | None
    staircase: str | None
    floor: str | None
    apartment: str | None
    intercom_code: str | None
    key_holder: str | None
    landmark: str | None
    call_window: str | None
    medic: MedicView
    caregivers: list[CaregiverView]


SENIOR_COLUMNS = SeniorPage.model_fields.keys() - {"medic", "caregivers"}


async def page(session: AsyncSession, senior: Senior) -> SeniorPage:
    medic = await session.get(User, senior.medic_id)
    caregivers = await session.execute(
        select(
            User.id.label("user_id"), User.display_name, Grant.relation, User.phone_e164
        )
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.senior_id == senior.id, Grant.role == Role.caregiver)
        .order_by(User.display_name, User.id)
    )
    return SeniorPage.model_validate(
        {
            **{name: getattr(senior, name) for name in SENIOR_COLUMNS},
            "medic": MedicView.model_validate(medic, from_attributes=True),
            "caregivers": [dict(c) for c in caregivers.mappings()],
        }
    )


@router.get("/seniors")
async def list_seniors(
    caller: AnyCaller, session: Db, role: Role | None = None
) -> list[SeniorRow]:
    """The seniors the caller reaches, newest first. `role` narrows the list to one
    role's reach and grants nothing (seniors SE6)."""
    seniors = await session.scalars(
        select(Senior)
        .where(reaches(caller, *([role] if role else [])))
        .order_by(Senior.created_at.desc(), Senior.id.desc())
    )
    return [SeniorRow.model_validate(s, from_attributes=True) for s in seniors]


@router.get("/seniors/{senior_id}")
async def get_senior(
    senior_id: uuid.UUID, caller: AnyCaller, session: Db
) -> SeniorPage:
    return await page(session, await reachable_senior(session, caller, senior_id))
```

- [ ] **Step 6: Include the router**

In `backend/app/main.py`, add the import. It sorts between `app.phones` and `app.settings`.

Find:

```python
from app.settings import check_environment, get_settings
```

Replace it with:

```python
from app.seniors import router as seniors
from app.settings import check_environment, get_settings
```

Then, at the bottom of the file:

Find:

```python
# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)
```

Replace it with:

```python
# Seniors, caregivers and enrollment have their own module (seniors SE16).
api.include_router(seniors)

# after every route is declared: include_router copies the routes it has at this point
app.include_router(api)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_reach.py -q`
Expected: `35 passed`.

Run: `uv run pytest -q`
Expected: `278 passed`.

- [ ] **Step 8: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add backend/app/reach.py backend/app/seniors.py backend/app/main.py backend/tests/conftest.py backend/tests/test_reach.py
git commit -F - <<'EOF'
backend: reach rule and the senior reads (auth-layer §3.6, seniors §3.1)

reaches() is the one SQL condition behind GET /seniors and
GET /seniors/{id}. A senior outside the caller's reach answers 404 (AL8).
?role= narrows the list to one role's reach.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 4: Register and edit a senior

**Files:**
- Create: `backend/tests/test_seniors.py`
- Modify: `backend/app/seniors.py`

**Interfaces:**
- Consumes: `user_for_number` (Task 1); the `/me` fields (Task 2); `reachable_senior(..., lock=True)`, `page`, `AsMedic`, `AsMedicOrDas`, `Db` and `router` (Task 3).
- Produces, in `app/seniors.py`:
  - `REQUIRED_TO_SUBMIT = ("street", "street_number")`, which Task 6 uses.
  - `required(max_length)` and `optional(max_length)`, field types. Task 5 uses `required`.
  - `SeniorBody`, the request model.
  - `def refused(status: int, reason: str, caller: Caller, senior_id: uuid.UUID, **extra) -> HTTPException`, which logs and builds a refusal. Tasks 5 and 6 use it.
  - `async def follow_number(session, senior, caller) -> None`.
  - `POST /api/seniors` and `PUT /api/seniors/{senior_id}`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_seniors.py`:

```python
"""Registering and editing a senior (seniors §3.4, §3.5; UC-01)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import EnrollmentState, Grant, Role, Senior, User

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
MOBILE = "+40700000005"
OTHER_MOBILE = "+40700000006"
LANDLINE = "+40256123456"

BODY = {
    "full_name": "Maria Popescu",
    "form_of_address": "doamna Maria",
    "phone": "0256 123 456",
}
ADDRESS = {"street": "Str. Daliei", "street_number": "12"}
SUBMITTED = {"enrollment_state": EnrollmentState.submitted, **ADDRESS}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refusal(reason: str, **extra) -> dict:
    return {"detail": {"reason": reason, **extra}}


@pytest.fixture
async def medic(db, add_user):
    user = await add_user(MEDIC, Role.medic, name="Dr. Ion Pop")
    user.practice = "CMI Dr. Pop"
    await db.commit()
    return user


@pytest.fixture
async def das(add_user):
    return await add_user(DAS, Role.das, name="DAS Test")


async def create(client, body=BODY, token=MEDIC):
    return await client.post("/api/seniors", json=body, headers=signed_in(token))


async def put(client, senior_id, body, token=MEDIC):
    return await client.put(
        f"/api/seniors/{senior_id}", json=body, headers=signed_in(token)
    )


async def me(client, token):
    return await client.get("/api/me", headers=signed_in(token))


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
async def test_refusals(client, medic, headers, status, reason):
    r = await client.post("/api/seniors", json=BODY, headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))
    r = await client.put(f"/api/seniors/{uuid.uuid4()}", json=BODY, headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))


async def test_only_a_medic_registers(client, das):
    r = await create(client, token=DAS)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))


async def test_a_role_refusal_comes_before_the_body(client, das):
    # seniors §3.1: identity, role, body, reach, state.
    r = await create(client, body={}, token=DAS)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))


async def test_a_bad_body_comes_before_reach(client, medic):
    r = await put(client, uuid.uuid4(), {})
    assert r.status_code == 422


async def test_a_draft_needs_three_fields(client, medic):
    r = await create(client)
    assert r.status_code == 201
    page = r.json()
    assert page == {
        "id": page["id"],
        "full_name": "Maria Popescu",
        "form_of_address": "doamna Maria",
        "phone_e164": LANDLINE,
        "phone_is_landline": True,
        "enrollment_state": "draft",
        "street": None,
        "street_number": None,
        "block": None,
        "staircase": None,
        "floor": None,
        "apartment": None,
        "intercom_code": None,
        "key_holder": None,
        "landmark": None,
        "call_window": None,
        "medic": {"display_name": "Dr. Ion Pop", "practice": "CMI Dr. Pop"},
        "caregivers": [],
    }
    read = await client.get(f"/api/seniors/{page['id']}", headers=signed_in(MEDIC))
    assert read.json() == page


async def test_a_landline_signs_nobody_in(client, db, medic):
    assert (await create(client)).status_code == 201
    users = select(func.count()).select_from(User).where(User.phone_e164 == LANDLINE)
    assert await db.scalar(users) == 0
    assert await db.scalar(select(func.count()).select_from(Grant)) == 1  # the medic's


async def test_a_mobile_makes_the_senior_grant(client, db, medic):
    r = await create(client, {**BODY, "phone": "0700 000 005"})
    assert (r.status_code, r.json()["phone_is_landline"]) == (201, False)
    signed = await me(client, MOBILE)
    assert signed.json() == {
        "display_name": "Maria Popescu",
        "phone_e164": MOBILE,
        "grants": [
            {
                "role": "senior",
                "senior_id": r.json()["id"],
                "senior_form_of_address": "doamna Maria",
                "relation": None,
            }
        ],
    }
    granted_by = select(Grant.granted_by).where(Grant.role == Role.senior)
    assert await db.scalar(granted_by) == medic.id


async def test_a_long_name_is_cut_for_the_user(client, db, medic):
    # seniors.full_name holds 200 characters, users.display_name 120.
    r = await create(client, {**BODY, "full_name": "A" * 150, "phone": MOBILE})
    assert (r.status_code, len(r.json()["full_name"])) == (201, 150)
    name = select(User.display_name).where(User.phone_e164 == MOBILE)
    assert await db.scalar(name) == "A" * 120


async def test_a_known_number_keeps_its_name(client, add_user, medic):
    await add_user(MOBILE, Role.medic, name="Dr. Maria Popescu")
    await create(client, {**BODY, "phone": MOBILE})
    signed = (await me(client, MOBILE)).json()
    assert signed["display_name"] == "Dr. Maria Popescu"
    assert [g["role"] for g in signed["grants"]] == ["medic", "senior"]


@pytest.mark.parametrize(
    "change",
    [
        {"full_name": "   "},
        {"full_name": "x" * 201},
        {"form_of_address": ""},
        {"form_of_address": "x" * 121},
        {"phone": "12345"},
        {"phone": None},
        {"street": "x" * 201},
        {"street_number": "x" * 21},
        {"intercom_code": "x" * 41},
        {"call_window": "x" * 61},
    ],
)
async def test_invalid_bodies(client, db, medic, change):
    r = await create(client, {**BODY, **change})
    assert r.status_code == 422
    assert await db.scalar(select(func.count()).select_from(Senior)) == 0


async def test_optional_fields_are_trimmed_and_a_blank_is_null(client, medic):
    r = await create(
        client, {**BODY, "street": "  Str. Daliei ", "block": "   ", "landmark": ""}
    )
    page = r.json()
    assert (page["street"], page["block"], page["landmark"]) == (
        "Str. Daliei",
        None,
        None,
    )


async def test_another_seniors_mobile_is_taken(client, db, medic):
    await create(client, {**BODY, "phone": MOBILE})
    r = await create(client, {**BODY, "full_name": "Ion Popescu", "phone": MOBILE})
    assert (r.status_code, r.json()) == (409, refusal("phone_taken"))
    assert await db.scalar(select(func.count()).select_from(Senior)) == 1


async def test_two_seniors_share_a_landline(client, db, medic):
    first = await create(client)
    second = await create(client, {**BODY, "full_name": "Ion Popescu"})
    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["id"] != second.json()["id"]


async def test_put_replaces_every_field(client, medic):
    made = await create(client, {**BODY, **ADDRESS, "landmark": "lângă farmacie"})
    r = await put(client, made.json()["id"], {**BODY, "full_name": "Maria Pop"})
    page = r.json()
    assert r.status_code == 200
    assert (page["full_name"], page["street"], page["landmark"]) == (
        "Maria Pop",
        None,
        None,
    )


async def test_put_moves_the_grant_with_the_number(client, medic):
    made = await create(client, {**BODY, "phone": MOBILE})
    r = await put(client, made.json()["id"], {**BODY, "phone": OTHER_MOBILE})
    assert (r.status_code, r.json()["phone_e164"]) == (200, OTHER_MOBILE)
    assert (await me(client, MOBILE)).json() == refusal("not_registered")
    assert [g["role"] for g in (await me(client, OTHER_MOBILE)).json()["grants"]] == [
        "senior"
    ]


async def test_put_to_a_landline_removes_the_grant(client, db, medic):
    made = await create(client, {**BODY, "phone": MOBILE})
    r = await put(client, made.json()["id"], BODY)
    assert (r.status_code, r.json()["phone_is_landline"]) == (200, True)
    assert (await me(client, MOBILE)).json() == refusal("not_registered")


async def test_put_from_a_landline_makes_the_grant(client, medic):
    made = await create(client)
    await put(client, made.json()["id"], {**BODY, "phone": MOBILE})
    assert (await me(client, MOBILE)).json()["grants"][0]["role"] == "senior"


async def test_put_with_the_same_number_keeps_the_grant(client, db, medic):
    made = await create(client, {**BODY, "phone": MOBILE})
    grant = select(Grant.id).where(Grant.role == Role.senior)
    before = await db.scalar(grant)
    r = await put(
        client, made.json()["id"], {**BODY, "phone": "0700 000 005", **ADDRESS}
    )
    assert r.status_code == 200
    assert await db.scalar(grant) == before


async def test_put_to_a_taken_number_changes_nothing(client, medic):
    await create(client, {**BODY, "phone": MOBILE})
    made = await create(
        client, {**BODY, "full_name": "Ion Popescu", "phone": OTHER_MOBILE}
    )
    senior_id = made.json()["id"]
    r = await put(client, senior_id, {**BODY, "full_name": "Changed", "phone": MOBILE})
    assert (r.status_code, r.json()) == (409, refusal("phone_taken"))
    read = await client.get(f"/api/seniors/{senior_id}", headers=signed_in(MEDIC))
    assert (read.json()["full_name"], read.json()["phone_e164"]) == (
        "Ion Popescu",
        OTHER_MOBILE,
    )
    assert (await me(client, OTHER_MOBILE)).json()["grants"][0][
        "senior_id"
    ] == senior_id


async def test_das_edits_a_submitted_senior(client, add_senior, medic, das):
    senior = await add_senior(LANDLINE, medic=medic, **SUBMITTED)
    r = await put(client, senior.id, {**BODY, **ADDRESS, "floor": "2"}, token=DAS)
    assert (r.status_code, r.json()["floor"]) == (200, "2")
    assert r.json()["enrollment_state"] == "submitted"


async def test_das_does_not_reach_a_draft(client, add_senior, medic, das):
    senior = await add_senior(LANDLINE, medic=medic)
    r = await put(client, senior.id, BODY, token=DAS)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


@pytest.mark.parametrize(
    ("body", "missing"),
    [
        ({**BODY, "street_number": "12"}, ["street"]),
        ({**BODY, "street": "Str. Daliei", "street_number": "  "}, ["street_number"]),
        (BODY, ["street", "street_number"]),
    ],
)
async def test_past_draft_the_address_stays(
    client, db, add_senior, medic, body, missing
):
    senior = await add_senior(LANDLINE, medic=medic, **SUBMITTED)
    r = await put(client, senior.id, body)
    assert (r.status_code, r.json()) == (422, refusal("missing_fields", fields=missing))
    await db.refresh(senior)
    assert (senior.street, senior.street_number) == ("Str. Daliei", "12")


async def test_a_draft_may_lose_its_address(client, add_senior, medic):
    senior = await add_senior(LANDLINE, medic=medic, **ADDRESS)
    r = await put(client, senior.id, BODY)
    assert (r.status_code, r.json()["street"]) == (200, None)


async def test_another_medic_is_told_not_found(client, add_user, add_senior, medic):
    await add_user(OTHER_MEDIC, Role.medic)
    senior = await add_senior(LANDLINE, medic=medic)
    r = await put(client, senior.id, BODY, token=OTHER_MEDIC)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


async def test_a_caregiver_cannot_edit(client, db, add_user, add_senior, medic):
    senior = await add_senior(LANDLINE, medic=medic)
    caregiver = await add_user(CAREGIVER)
    db.add(Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=senior.id))
    await db.commit()
    r = await put(client, senior.id, BODY, token=CAREGIVER)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_seniors.py -q`
Expected: `39 failed`. `POST` and `PUT` answer 405 `Method Not Allowed`.

- [ ] **Step 3: Replace the imports of `app/seniors.py`**

In `backend/app/seniors.py`, replace the import block, from `import logging` down to `from app.reach import reachable_senior, reaches`, with:

```python
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, BeforeValidator, StringConstraints, field_validator
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Caller, current_caller, refuse, require_roles
from app.db import get_session
from app.grants import user_for_number
from app.models import EnrollmentState, Grant, Role, Senior, User
from app.phones import is_mobile, normalize
from app.reach import reachable_senior, reaches
```

- [ ] **Step 4: Append the registration section**

Append to the end of `backend/app/seniors.py`, after two blank lines:

```python
# What a submit needs beyond the draft's own required fields (seniors SE4).
REQUIRED_TO_SUBMIT = ("street", "street_number")
# users.display_name is shorter than seniors.full_name (05 §1).
USER_NAME_LENGTH = 120


def blank_to_none(value: Any) -> Any:
    """An optional field left empty in a form is no value, not an empty string."""
    if isinstance(value, str):
        return value.strip() or None
    return value


def required(max_length: int) -> Any:
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length),
    ]


def optional(max_length: int) -> Any:
    # The limit sits on the text, not on the whole field: a constraint on `str | None`
    # is also applied to the None a blank becomes, and fails.
    text = Annotated[str, StringConstraints(max_length=max_length)]
    return Annotated[text | None, BeforeValidator(blank_to_none)]


class SeniorBody(BaseModel):
    """The registration, for POST and PUT /seniors (seniors §3.5). PUT replaces every
    field, so one left out becomes null."""

    full_name: required(200)
    form_of_address: required(120)
    phone: str
    street: optional(200) = None
    street_number: optional(20) = None
    block: optional(20) = None
    staircase: optional(20) = None
    floor: optional(20) = None
    apartment: optional(20) = None
    intercom_code: optional(40) = None
    key_holder: optional(200) = None
    landmark: optional(200) = None
    call_window: optional(60) = None

    @field_validator("phone")
    @classmethod
    def e164(cls, raw: str) -> str:
        # A landline is fine: the senior is called, and need not sign in.
        return normalize(raw)


def refused(
    status: int, reason: str, caller: Caller, senior_id: uuid.UUID, **extra: Any
) -> HTTPException:
    """A refusal about one senior, logged with the user id (auth-layer AL15). The
    request's transaction is rolled back when its session closes, so a refused
    command changes nothing."""
    log.info("refused %s: user %s, senior %s", reason, caller.user.id, senior_id)
    return refuse(status, reason, **extra)


def registration(body: SeniorBody) -> dict[str, Any]:
    """The body as seniors columns. Landline or not is worked out from the number."""
    return {
        **body.model_dump(exclude={"phone"}),
        "phone_e164": body.phone,
        "phone_is_landline": not is_mobile(body.phone),
    }


async def follow_number(session: AsyncSession, senior: Senior, caller: Caller) -> None:
    """The senior's grant follows the senior's number (seniors SE10, SE11).

    Called when the number is new or has changed: drops this senior's grant, then
    makes one for a mobile. A landline signs nobody in.
    """
    await session.execute(
        delete(Grant).where(Grant.role == Role.senior, Grant.senior_id == senior.id)
    )
    if senior.phone_is_landline:
        return
    user = await user_for_number(
        session, senior.phone_e164, senior.full_name[:USER_NAME_LENGTH]
    )
    # ON CONFLICT with no target: the at-most-one-senior-grant-per-user index stops
    # a number that already signs in as another senior, even of two saves at once.
    granted = await session.scalar(
        insert(Grant)
        .values(
            user_id=user.id,
            role=Role.senior,
            senior_id=senior.id,
            granted_by=caller.user.id,
        )
        .on_conflict_do_nothing()
        .returning(Grant.id)
    )
    if granted is None:
        raise refused(409, "phone_taken", caller, senior.id)


@router.post("/seniors", status_code=201)
async def create_senior(body: SeniorBody, caller: AsMedic, session: Db) -> SeniorPage:
    """A new senior in draft, registered by the caller (UC-01). Not repeat-safe: two
    posts make two drafts (seniors SE14)."""
    senior = Senior(medic_id=caller.user.id, **registration(body))
    session.add(senior)
    await session.flush()  # the database makes the id
    await follow_number(session, senior, caller)
    await session.commit()
    return await page(session, senior)


@router.put("/seniors/{senior_id}")
async def update_senior(
    senior_id: uuid.UUID, body: SeniorBody, caller: AsMedicOrDas, session: Db
) -> SeniorPage:
    """Replaces the registration, in any state (seniors SE9)."""
    # Locked, so a submit at the same moment sees either the old row or the new one.
    senior = await reachable_senior(
        session, caller, senior_id, Role.medic, Role.das, lock=True
    )
    if senior.enrollment_state != EnrollmentState.draft:
        missing = [name for name in REQUIRED_TO_SUBMIT if getattr(body, name) is None]
        if missing:
            raise refused(422, "missing_fields", caller, senior_id, fields=missing)
    number_changed = body.phone != senior.phone_e164
    for name, value in registration(body).items():
        setattr(senior, name, value)
    if number_changed:
        await session.flush()
        await follow_number(session, senior, caller)
    await session.commit()
    return await page(session, senior)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_seniors.py -q`
Expected: `39 passed`.

Run: `uv run pytest -q`
Expected: `317 passed`.

- [ ] **Step 6: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/seniors.py backend/tests/test_seniors.py
git commit -F - <<'EOF'
backend: register and edit a senior (UC-01, seniors §3.4)

POST /seniors makes a draft from a name, a form of address and a phone
number. PUT replaces the registration, for the medic or for DAS, in any
state. The senior's grant follows the number, and a mobile that is
already another senior's is refused with phone_taken.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 5: Caregivers

**Files:**
- Create: `backend/tests/test_caregivers.py`
- Modify: `backend/app/seniors.py`

**Interfaces:**
- Consumes: `user_for_number` (Task 1); `reachable_senior`, `CaregiverView`, `AsMedicOrDas`, `Db`, `router` (Task 3); `required`, `refused` and `POST /api/seniors` (Task 4).
- Produces: `CaregiverBody`; `POST /api/seniors/{senior_id}/caregivers`, which answers 201 with a `CaregiverView`; `DELETE /api/seniors/{senior_id}/caregivers/{user_id}`, which answers 204.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_caregivers.py`:

```python
"""A senior's caregivers (seniors §3.4, §3.5; UC-01 step 3)."""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.models import EnrollmentState, Grant, Role, User

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
LANDLINE = "+40256123456"

BODY = {"display_name": "Ioana Pop", "relation": "fiică", "phone": "0700 000 004"}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refusal(reason: str) -> dict:
    return {"detail": {"reason": reason}}


@pytest.fixture
async def medic(add_user):
    return await add_user(MEDIC, Role.medic, name="Dr. Ion Pop")


@pytest.fixture
async def senior(add_senior, medic):
    return await add_senior(LANDLINE, medic=medic)


async def add(client, senior_id, body=BODY, token=MEDIC):
    return await client.post(
        f"/api/seniors/{senior_id}/caregivers", json=body, headers=signed_in(token)
    )


async def remove(client, senior_id, user_id, token=MEDIC):
    return await client.delete(
        f"/api/seniors/{senior_id}/caregivers/{user_id}", headers=signed_in(token)
    )


async def me(client, token=CAREGIVER):
    return await client.get("/api/me", headers=signed_in(token))


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
async def test_refusals(client, senior, headers, status, reason):
    path = f"/api/seniors/{senior.id}/caregivers"
    r = await client.post(path, json=BODY, headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))
    r = await client.delete(f"{path}/{uuid.uuid4()}", headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))


async def test_add_a_caregiver(client, db, medic, senior):
    r = await add(client, senior.id)
    assert r.status_code == 201
    assert r.json() == {
        "user_id": r.json()["user_id"],
        "display_name": "Ioana Pop",
        "relation": "fiică",
        "phone_e164": CAREGIVER,
    }
    grant = await db.scalar(select(Grant).where(Grant.role == Role.caregiver))
    assert (grant.senior_id, grant.relation, grant.granted_by) == (
        senior.id,
        "fiică",
        medic.id,
    )
    page = await client.get(f"/api/seniors/{senior.id}", headers=signed_in(MEDIC))
    assert page.json()["caregivers"] == [r.json()]


async def test_the_caregiver_signs_in_and_sees_only_her(client, add_senior, senior):
    await add_senior("+40256000009", name="Someone Else")
    await add(client, senior.id)
    assert (await me(client)).json()["grants"] == [
        {
            "role": "caregiver",
            "senior_id": str(senior.id),
            "senior_form_of_address": "doamna Maria",
            "relation": "fiică",
        }
    ]
    r = await client.get("/api/seniors", headers=signed_in(CAREGIVER))
    assert [s["id"] for s in r.json()] == [str(senior.id)]


async def test_a_known_number_keeps_its_name(client, add_user, senior):
    await add_user(CAREGIVER, Role.medic, name="Dr. Ioana Pop")
    r = await add(client, senior.id)
    assert (r.status_code, r.json()["display_name"]) == (201, "Dr. Ioana Pop")


@pytest.mark.parametrize(
    "change",
    [
        {"phone": "0256 123 456"},  # a landline cannot receive the sign-in SMS
        {"phone": "12345"},
        {"relation": "   "},
        {"relation": "x" * 61},
        {"display_name": ""},
        {"display_name": "x" * 121},
    ],
)
async def test_invalid_bodies(client, db, senior, change):
    r = await add(client, senior.id, {**BODY, **change})
    assert r.status_code == 422
    assert await db.scalar(select(Grant).where(Grant.role == Role.caregiver)) is None


async def test_a_repeat_changes_nothing(client, db, senior):
    await add(client, senior.id)
    r = await add(client, senior.id, {**BODY, "relation": "soră"})
    assert (r.status_code, r.json()) == (409, refusal("already_done"))
    relation = select(Grant.relation).where(Grant.role == Role.caregiver)
    assert (await db.scalars(relation)).all() == ["fiică"]


async def test_two_adds_at_once(client, senior):
    first, second = await asyncio.gather(add(client, senior.id), add(client, senior.id))
    assert sorted([first.status_code, second.status_code]) == [201, 409]


async def test_the_seniors_own_mobile_can_care(client, medic):
    # A senior who uses a relative's phone (01 §6, seniors SE12).
    made = await client.post(
        "/api/seniors",
        json={
            "full_name": "Maria Popescu",
            "form_of_address": "doamna Maria",
            "phone": CAREGIVER,
        },
        headers=signed_in(MEDIC),
    )
    senior_id = made.json()["id"]
    r = await add(client, senior_id)
    assert r.status_code == 201
    assert [g["role"] for g in (await me(client)).json()["grants"]] == [
        "caregiver",
        "senior",
    ]
    # Removing the caregiver grant leaves the senior's own.
    assert (await remove(client, senior_id, r.json()["user_id"])).status_code == 204
    assert [g["role"] for g in (await me(client)).json()["grants"]] == ["senior"]


async def test_removed_caregiver_is_not_registered(client, db, senior):
    added = await add(client, senior.id)
    r = await remove(client, senior.id, added.json()["user_id"])
    assert (r.status_code, r.content) == (204, b"")
    assert ((await me(client)).status_code, (await me(client)).json()) == (
        403,
        refusal("not_registered"),
    )
    # The user row stays (seniors §3.5).
    assert await db.scalar(select(User.id).where(User.phone_e164 == CAREGIVER))
    page = await client.get(f"/api/seniors/{senior.id}", headers=signed_in(MEDIC))
    assert page.json()["caregivers"] == []


async def test_removing_keeps_their_other_grants(
    client, add_user, add_senior, medic, senior
):
    await add_user(CAREGIVER, Role.medic)
    father = await add_senior("+40256000009", name="Ion Pop", medic=medic)
    added = await add(client, senior.id)
    await add(client, father.id)
    await remove(client, senior.id, added.json()["user_id"])
    grants = (await me(client)).json()["grants"]
    assert [(g["role"], g["senior_id"]) for g in grants] == [
        ("medic", None),
        ("caregiver", str(father.id)),
    ]


async def test_removing_someone_who_is_not_her_caregiver(
    client, add_senior, medic, senior
):
    r = await remove(client, senior.id, uuid.uuid4())
    assert (r.status_code, r.json()) == (404, refusal("not_found"))
    # A caregiver of another senior is not this senior's.
    other = await add_senior("+40256000009", name="Ion Pop", medic=medic)
    added = await add(client, other.id)
    r = await remove(client, senior.id, added.json()["user_id"])
    assert (r.status_code, r.json()) == (404, refusal("not_found"))
    # And a second removal finds nothing to remove.
    await remove(client, other.id, added.json()["user_id"])
    r = await remove(client, other.id, added.json()["user_id"])
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


async def test_das_manages_caregivers_once_submitted(
    client, db, add_user, add_senior, medic, senior
):
    await add_user(DAS, Role.das)
    r = await add(client, senior.id, token=DAS)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))  # a draft
    sent = await add_senior(
        "+40256000009", medic=medic, enrollment_state=EnrollmentState.submitted
    )
    added = await add(client, sent.id, token=DAS)
    assert added.status_code == 201
    r = await remove(client, sent.id, added.json()["user_id"], token=DAS)
    assert r.status_code == 204


async def test_another_medic_is_told_not_found(client, add_user, senior):
    await add_user(OTHER_MEDIC, Role.medic)
    r = await add(client, senior.id, token=OTHER_MEDIC)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))
    r = await remove(client, senior.id, uuid.uuid4(), token=OTHER_MEDIC)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


async def test_a_caregiver_cannot_add_or_remove(client, senior):
    added = await add(client, senior.id)
    r = await add(client, senior.id, {**BODY, "phone": "0700 000 006"}, token=CAREGIVER)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
    r = await remove(client, senior.id, added.json()["user_id"], token=CAREGIVER)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_caregivers.py -q`
Expected: `22 failed`. The caregiver paths answer 404 `Not Found`.

- [ ] **Step 3: Append the caregivers section**

The imports of `backend/app/seniors.py` do not change in this task. Append to the end of the file, after two blank lines:

```python
class CaregiverBody(BaseModel):
    """POST /seniors/{id}/caregivers' body (seniors §3.5)."""

    display_name: required(120)
    relation: required(60)
    phone: str

    @field_validator("phone")
    @classmethod
    def mobile_e164(cls, raw: str) -> str:
        e164 = normalize(raw)
        if not is_mobile(e164):
            raise ValueError("a caregiver signs in by SMS: the number must be a mobile")
        return e164


@router.post("/seniors/{senior_id}/caregivers", status_code=201)
async def add_caregiver(
    senior_id: uuid.UUID, body: CaregiverBody, caller: AsMedicOrDas, session: Db
) -> CaregiverView:
    """Makes the caregiver grant; the number can sign in at once (UC-01 step 3)."""
    senior = await reachable_senior(session, caller, senior_id, Role.medic, Role.das)
    user = await user_for_number(session, body.phone, body.display_name)
    granted = await session.scalar(
        insert(Grant)
        .values(
            user_id=user.id,
            role=Role.caregiver,
            senior_id=senior.id,
            relation=body.relation,
            granted_by=caller.user.id,
        )
        .on_conflict_do_nothing()
        .returning(Grant.id)
    )
    if granted is None:
        raise refused(409, "already_done", caller, senior_id)
    await session.commit()
    return CaregiverView(
        user_id=user.id,
        display_name=user.display_name,
        relation=body.relation,
        phone_e164=user.phone_e164,
    )


@router.delete("/seniors/{senior_id}/caregivers/{user_id}", status_code=204)
async def remove_caregiver(
    senior_id: uuid.UUID, user_id: uuid.UUID, caller: AsMedicOrDas, session: Db
) -> None:
    """Deletes that caregiver grant, so access stops at once (05 §5). The user row and
    their other grants stay."""
    senior = await reachable_senior(session, caller, senior_id, Role.medic, Role.das)
    removed = await session.execute(
        delete(Grant)
        .where(
            Grant.senior_id == senior.id,
            Grant.role == Role.caregiver,
            Grant.user_id == user_id,
        )
        .returning(Grant.id)
    )
    if removed.first() is None:
        raise refused(404, "not_found", caller, senior_id)
    await session.commit()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_caregivers.py -q`
Expected: `22 passed`.

Run: `uv run pytest -q`
Expected: `339 passed`.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/seniors.py backend/tests/test_caregivers.py
git commit -F - <<'EOF'
backend: add and remove caregivers (UC-01 step 3, seniors §3.4)

A caregiver is a grant: name, relation and a mobile number. Removing it
deletes only that grant, so access stops at once and the person's other
grants stay. The medic or DAS may do either, in any state.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 6: Enrollment states

**Files:**
- Create: `backend/tests/test_enrollment.py`
- Modify: `backend/app/seniors.py`

**Interfaces:**
- Consumes: `reachable_senior`, `page`, `SeniorRow`, `AsMedic`, `AsDas`, `Db`, `router` (Task 3); `REQUIRED_TO_SUBMIT`, `refused` (Task 4); the caregiver routes (Task 5), for the story test.
- Produces: `async def move(session, senior, expected, to) -> bool`; `GET /api/enrollments`; `POST /api/seniors/{senior_id}/submit`; `POST /api/seniors/{senior_id}/accept`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_enrollment.py`:

```python
"""Enrollment states: submit, accept and GET /enrollments (seniors §3.4; UC-01 step 6,
UC-04 step 1)."""

import asyncio
import uuid

import pytest

from app.models import EnrollmentState, Role

DAS = "+40700000001"
MEDIC = "+40700000002"
OTHER_MEDIC = "+40700000003"
CAREGIVER = "+40700000004"
LANDLINE = "+40256123456"
ADDRESS = {"street": "Str. Daliei", "street_number": "12"}


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refusal(reason: str, **extra) -> dict:
    return {"detail": {"reason": reason, **extra}}


@pytest.fixture
async def medic(add_user):
    return await add_user(MEDIC, Role.medic, name="Dr. Ion Pop")


@pytest.fixture
async def das(add_user):
    return await add_user(DAS, Role.das, name="DAS Test")


@pytest.fixture
async def draft(add_senior, medic):
    return await add_senior(LANDLINE, medic=medic, **ADDRESS)


async def submit(client, senior_id, token=MEDIC):
    return await client.post(
        f"/api/seniors/{senior_id}/submit", headers=signed_in(token)
    )


async def accept(client, senior_id, token=DAS):
    return await client.post(
        f"/api/seniors/{senior_id}/accept", headers=signed_in(token)
    )


async def enrollments(client):
    r = await client.get("/api/enrollments", headers=signed_in(DAS))
    assert r.status_code == 200
    return [s["full_name"] for s in r.json()]


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/seniors/{id}/submit"),
        ("POST", "/api/seniors/{id}/accept"),
        ("GET", "/api/enrollments"),
    ],
)
async def test_refusals(client, draft, method, path, headers, status, reason):
    r = await client.request(method, path.format(id=draft.id), headers=headers)
    assert (r.status_code, r.json()) == (status, refusal(reason))


async def test_submit(client, draft):
    r = await submit(client, draft.id)
    assert (r.status_code, r.json()["enrollment_state"]) == (200, "submitted")
    assert r.json()["id"] == str(draft.id)


@pytest.mark.parametrize(
    ("address", "missing"),
    [
        ({"street_number": "12"}, ["street"]),
        ({"street": "Str. Daliei"}, ["street_number"]),
        ({}, ["street", "street_number"]),
    ],
)
async def test_submit_needs_the_address(
    client, db, add_senior, medic, address, missing
):
    senior = await add_senior(LANDLINE, medic=medic, **address)
    r = await submit(client, senior.id)
    assert (r.status_code, r.json()) == (422, refusal("missing_fields", fields=missing))
    await db.refresh(senior)
    assert senior.enrollment_state == EnrollmentState.draft


async def test_a_second_submit_is_refused(client, draft):
    await submit(client, draft.id)
    r = await submit(client, draft.id)
    assert (r.status_code, r.json()) == (409, refusal("wrong_state"))


async def test_two_submits_at_once(client, draft):
    first, second = await asyncio.gather(
        submit(client, draft.id), submit(client, draft.id)
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]


async def test_das_sees_her_once_submitted(client, draft, das):
    page = f"/api/seniors/{draft.id}"
    assert (await client.get(page, headers=signed_in(DAS))).status_code == 404
    assert await enrollments(client) == []
    await submit(client, draft.id)
    assert (await client.get(page, headers=signed_in(DAS))).status_code == 200
    assert await enrollments(client) == ["Maria Pop"]


async def test_enrollments_are_oldest_first(client, add_senior, medic, das):
    submitted = EnrollmentState.submitted
    await add_senior("+40256000001", "First", medic, enrollment_state=submitted)
    await add_senior("+40256000002", "Second", medic, enrollment_state=submitted)
    await add_senior("+40256000003", "Still a draft", medic)
    assert await enrollments(client) == ["First", "Second"]


async def test_accept(client, draft, das):
    await submit(client, draft.id)
    r = await accept(client, draft.id)
    assert (r.status_code, r.json()["enrollment_state"]) == (200, "accepted")
    assert await enrollments(client) == []
    # A second accept is refused (seniors SE13).
    r = await accept(client, draft.id)
    assert (r.status_code, r.json()) == (409, refusal("wrong_state"))


async def test_two_accepts_at_once(client, draft, das):
    await submit(client, draft.id)
    first, second = await asyncio.gather(
        accept(client, draft.id), accept(client, draft.id)
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]


async def test_a_draft_is_outside_das_reach(client, draft, das):
    r = await accept(client, draft.id)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))
    r = await accept(client, uuid.uuid4())
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


async def test_only_das_accepts_and_only_a_medic_submits(client, draft, das):
    r = await submit(client, draft.id, token=DAS)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
    await submit(client, draft.id)
    r = await accept(client, draft.id, token=MEDIC)
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))
    r = await client.get("/api/enrollments", headers=signed_in(MEDIC))
    assert (r.status_code, r.json()) == (403, refusal("not_allowed"))


async def test_another_medic_cannot_submit_her(client, add_user, draft):
    await add_user(OTHER_MEDIC, Role.medic)
    r = await submit(client, draft.id, token=OTHER_MEDIC)
    assert (r.status_code, r.json()) == (404, refusal("not_found"))


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/seniors"),
        ("GET", "/api/seniors/{id}"),
        ("POST", "/api/seniors"),
        ("PUT", "/api/seniors/{id}"),
        ("POST", "/api/seniors/{id}/caregivers"),
        ("DELETE", "/api/seniors/{id}/caregivers/{id}"),
        ("POST", "/api/seniors/{id}/submit"),
        ("POST", "/api/seniors/{id}/accept"),
        ("GET", "/api/enrollments"),
    ],
)
async def test_a_user_with_no_grant_left_is_not_registered(
    client, add_user, draft, method, path
):
    # Every senior endpoint, now that they all exist (seniors §6.4, the second row).
    await add_user(CAREGIVER)  # a user row whose grants were all removed
    r = await client.request(
        method, path.format(id=draft.id), headers=signed_in(CAREGIVER)
    )
    assert (r.status_code, r.json()) == (403, refusal("not_registered"))


async def test_the_story(client, add_user, medic, das):
    """seniors §1, steps 2 to 6, through the API alone."""
    await add_user(OTHER_MEDIC, Role.medic)
    as_medic, as_das = signed_in(MEDIC), signed_in(DAS)
    as_caregiver = signed_in(CAREGIVER)

    # 2. The medic registers doamna Maria with a caregiver, and submits.
    made = await client.post(
        "/api/seniors",
        json={
            "full_name": "Maria Popescu",
            "form_of_address": "doamna Maria",
            "phone": "0256 123 456",
            **ADDRESS,
        },
        headers=as_medic,
    )
    page = f"/api/seniors/{made.json()['id']}"
    added = await client.post(
        f"{page}/caregivers",
        json={
            "display_name": "Ioana Pop",
            "relation": "fiică",
            "phone": "0700 000 004",
        },
        headers=as_medic,
    )
    assert (made.status_code, added.status_code) == (201, 201)

    # 5a. DAS cannot see a draft.
    assert (await client.get(page, headers=as_das)).status_code == 404
    assert (await client.post(f"{page}/submit", headers=as_medic)).status_code == 200

    # 3. The caregiver's /me names her, and their list holds only her.
    grant = (await client.get("/api/me", headers=as_caregiver)).json()["grants"][0]
    assert grant["senior_form_of_address"] == "doamna Maria"
    seniors = (await client.get("/api/seniors", headers=as_caregiver)).json()
    assert [s["id"] for s in seniors] == [made.json()["id"]]

    # 4. Another medic gets 404 for her.
    assert (await client.get(page, headers=signed_in(OTHER_MEDIC))).status_code == 404

    # 5b. DAS sees her now, accepts her, and a second accept is refused.
    assert (await client.get(page, headers=as_das)).status_code == 200
    assert (await client.post(f"{page}/accept", headers=as_das)).status_code == 200
    assert (await client.post(f"{page}/accept", headers=as_das)).status_code == 409

    # 6. The medic removes the caregiver; their next request is not_registered.
    removed = await client.delete(
        f"{page}/caregivers/{added.json()['user_id']}", headers=as_medic
    )
    assert removed.status_code == 204
    r = await client.get("/api/seniors", headers=as_caregiver)
    assert (r.status_code, r.json()) == (403, refusal("not_registered"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_enrollment.py -q`
Expected: `29 failed, 6 passed`. The six are the cases of `test_a_user_with_no_grant_left_is_not_registered` for the endpoints Tasks 3 to 5 already built.

- [ ] **Step 3: Add one import**

In `backend/app/seniors.py`:

Find:

```python
from sqlalchemy import delete, select
```

Replace it with:

```python
from sqlalchemy import delete, select, update
```

- [ ] **Step 4: Append the enrollment section**

Append to the end of `backend/app/seniors.py`, after two blank lines:

```python
async def move(
    session: AsyncSession,
    senior: Senior,
    expected: EnrollmentState,
    to: EnrollmentState,
) -> bool:
    """Changes the state only where it is still `expected`, so of two at the same
    moment one wins (seniors §3.5). False when nothing moved."""
    conditions = [Senior.id == senior.id, Senior.enrollment_state == expected]
    if to == EnrollmentState.submitted:
        conditions += [
            getattr(Senior, name).is_not(None) for name in REQUIRED_TO_SUBMIT
        ]
    moved = await session.execute(
        update(Senior)
        .where(*conditions)
        .values(enrollment_state=to)
        .returning(Senior.id)
    )
    if moved.first() is None:
        return False
    await session.commit()
    return True


@router.get("/enrollments")
async def list_enrollments(_: AsDas, session: Db) -> list[SeniorRow]:
    """Seniors waiting for DAS, oldest first (UC-04 step 1)."""
    seniors = await session.scalars(
        select(Senior)
        .where(Senior.enrollment_state == EnrollmentState.submitted)
        .order_by(Senior.created_at, Senior.id)
    )
    return [SeniorRow.model_validate(s, from_attributes=True) for s in seniors]


@router.post("/seniors/{senior_id}/submit")
async def submit_senior(
    senior_id: uuid.UUID, caller: AsMedic, session: Db
) -> SeniorPage:
    """draft -> submitted: the senior now waits for DAS (UC-01 step 6)."""
    senior = await reachable_senior(session, caller, senior_id, Role.medic)
    if not await move(
        session, senior, EnrollmentState.draft, EnrollmentState.submitted
    ):
        await session.refresh(senior)
        if senior.enrollment_state != EnrollmentState.draft:
            raise refused(409, "wrong_state", caller, senior_id)
        missing = [name for name in REQUIRED_TO_SUBMIT if getattr(senior, name) is None]
        raise refused(422, "missing_fields", caller, senior_id, fields=missing)
    await session.refresh(senior)
    return await page(session, senior)


@router.post("/seniors/{senior_id}/accept")
async def accept_senior(senior_id: uuid.UUID, caller: AsDas, session: Db) -> SeniorPage:
    """submitted -> accepted (UC-04 step 1). It queues nothing until the welcome call
    exists, and nobody is stored as the accepter (seniors SE15)."""
    senior = await reachable_senior(session, caller, senior_id, Role.das)
    if not await move(
        session, senior, EnrollmentState.submitted, EnrollmentState.accepted
    ):
        raise refused(409, "wrong_state", caller, senior_id)
    log.info("accepted: user %s, senior %s", caller.user.id, senior_id)
    await session.refresh(senior)
    return await page(session, senior)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_enrollment.py -q`
Expected: `35 passed`.

Run: `uv run pytest -q`
Expected: `374 passed`.

- [ ] **Step 6: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/seniors.py backend/tests/test_enrollment.py
git commit -F - <<'EOF'
backend: enrollment states: submit, accept, GET /enrollments (UC-01, UC-04)

draft -> submitted needs a street and a street number; submitted ->
accepted is DAS's and queues nothing until the welcome call exists. Each
moves the state only where it is still the expected one, so a repeat, or
the loser of two at once, gets wrong_state.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 7: `GET /staff`

**Files:**
- Modify: `backend/tests/test_staff.py`
- Modify: `backend/app/staff.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `user_for_number` in `staff.py` (Task 1); `ROLE_ORDER` from `app/models.py`.
- Produces: `STAFF_ROLES`; `async def list_staff(session: AsyncSession) -> list[tuple[User, list[str]]]`; the model `StaffRow`; `GET /api/staff`, which the dashboard slice calls.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_staff.py`:

Append to the end of the file:

```python
async def list_staff(client, token=DAS):
    return await client.get("/api/staff", headers=signed_in(token))


async def test_staff_lists_das_and_medics_by_name(
    client, db, add_user, add_senior, das
):
    await add_user("+40700000003", Role.medic, Role.das, name="Ana Pop")
    medic = await add_user("+40700000002", Role.medic, name="Bogdan Ene")
    # A caregiver is not staff, and a staff member's caregiver grant is not a staff role.
    senior = await add_senior("+40256000001")
    caregiver = await add_user("+40700000004", name="Carmen Stan")
    db.add_all(
        Grant(user_id=u.id, role=Role.caregiver, senior_id=senior.id)
        for u in (caregiver, medic)
    )
    medic.practice = "CMI Dr. Ene"
    await db.commit()
    r = await list_staff(client)
    assert r.status_code == 200
    assert [(p["display_name"], p["roles"]) for p in r.json()] == [
        ("Ana Pop", ["das", "medic"]),
        ("Bogdan Ene", ["medic"]),
        ("DAS Test", ["das"]),
        ("Medic", ["medic"]),  # add_senior's own medic
    ]
    assert r.json()[1] == {
        "id": str(medic.id),
        "display_name": "Bogdan Ene",
        "phone_e164": "+40700000002",
        "practice": "CMI Dr. Ene",
        "roles": ["medic"],
    }


async def test_a_new_grant_shows_in_the_list(client, das):
    await post(client, MEDIC)
    names = [p["display_name"] for p in (await list_staff(client)).json()]
    assert names == ["DAS Test", "Dr. Ion Pop"]


async def test_only_das_lists_staff(client, add_user):
    await add_user("+40700000003", Role.medic)
    r = await list_staff(client, token="+40700000003")
    assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_allowed"}})


@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("invalid"), 401, "not_signed_in"),
        (signed_in("no-phone"), 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
        (signed_in("+40700000004"), 403, "not_registered"),  # a user with no grant left
    ],
)
async def test_list_refusals(client, add_user, das, headers, status, reason):
    await add_user("+40700000004")
    r = await client.get("/api/staff", headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_staff.py -q`
Expected: `8 failed, 20 passed`. `GET /api/staff` answers 405 `Method Not Allowed`, because only `POST` exists.

- [ ] **Step 3: List staff in `app/staff.py`**

In `backend/app/staff.py`, the docstring:

Find:

```python
"""Granting staff roles (UC-14, auth-layer §3.4), for POST /staff and grant_das.py."""
```

Replace it with:

```python
"""Staff roles (UC-14): granting them, for POST /staff and grant_das.py (auth-layer
§3.4), and listing who holds them, for GET /staff (04 §1)."""
```

The imports, with `select` back and the roles named:

Find:

```python
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.grants import user_for_number
from app.models import Grant, Role, User
```

Replace it with:

```python
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.grants import user_for_number
from app.models import ROLE_ORDER, Grant, Role, User

# The roles DAS grants (UC-14). GET /staff lists who holds them.
STAFF_ROLES = (Role.das, Role.medic)
```

And the function:

Append to the end of the file:

```python
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
```

- [ ] **Step 4: Add the route**

In `backend/app/main.py`:

Find:

```python
from app.staff import grant_staff
```

Replace it with:

```python
from app.staff import grant_staff, list_staff
```

Then put the model and the route after `grant_staff_member`, just before the incidents:

Find:

```python
# One row of GET /incidents (04 §1). Names follow the incidents and seniors tables (05 §1)
```

Replace it with:

```python
class StaffRow(BaseModel):
    """One person in GET /staff (seniors §3.3). On duty joins it with the hand-over
    work (P10)."""

    id: uuid.UUID
    display_name: str
    phone_e164: str
    practice: str | None
    roles: list[str]


@api.get("/staff")
async def list_staff_members(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[StaffRow]:
    """DAS employees and medics, for the dashboard's „Personal” (UC-14)."""
    return [
        StaffRow(
            id=user.id,
            display_name=user.display_name,
            phone_e164=user.phone_e164,
            practice=user.practice,
            roles=roles,
        )
        for user, roles in await list_staff(session)
    ]


# One row of GET /incidents (04 §1). Names follow the incidents and seniors tables (05 §1)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_staff.py -q`
Expected: `28 passed`.

Run: `uv run pytest -q`
Expected: `382 passed`.

- [ ] **Step 6: Lint**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/staff.py backend/app/main.py backend/tests/test_staff.py
git commit -F - <<'EOF'
backend: GET /staff for the dashboard's Personal screen (UC-14)

DAS employees and medics by name, each with their staff roles. On duty
joins the response with the hand-over work (P10).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 8: Bring the docs in line

The contract and the docs move together (root `AGENTS.md`). These are the changes of spec §6.6, plus the test numbers in `backend/README.md`, which lists them too.

**Files:**
- Modify: `docs/specs/sentinela/04-interfaces.md`
- Modify: `docs/specs/sentinela/01-architecture.md`
- Modify: `docs/specs/sentinela/02-use-cases.md`
- Modify: `docs/specs/sentinela/05-data-model.md`
- Modify: `docs/specs/auth-layer.md`
- Modify: `docs/specs/seniors-and-enrollment.md`
- Modify: `backend/AGENTS.md`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: the endpoints as built in Tasks 2 to 7.
- Produces: nothing that code reads.

Each "Find" text occurs exactly once in its file. Copy it; do not retype it, because some rows contain the Romanian quotes „ and ”.

- [ ] **Step 1: `docs/specs/sentinela/04-interfaces.md`, §0**

Find:

````markdown
- **Repeat-safe.** Every command and every event can be sent twice without a second effect. Commands that queue a call return the existing call if one is already queued or live for that senior.
````

Replace it with:

````markdown
- **Repeat-safe.** Every command and every event can be sent twice without a second effect. Commands that queue a call return the existing call if one is already queued or live for that senior. The one exception is `POST /seniors`: two posts make two drafts, so a client creates a draft once and then saves it with `PUT` ([seniors-and-enrollment.md](../seniors-and-enrollment.md) SE14).
````

In the "Refusals" bullet of the same section:

Find:

````markdown
`wrong_state` and `already_done` (409), `unknown_status` (422, a status filter naming no known status),
````

Replace it with:

````markdown
`wrong_state`, `already_done` and `phone_taken` (409, the last for a mobile number that is already another senior's), `unknown_status` (422, a status filter naming no known status), `missing_fields` (422, with the missing `fields` listed),
````

- [ ] **Step 2: `04-interfaces.md`, §1**

Find:

````markdown
| My profile | `GET /me` | Any number with a grant | Display name, phone number, and one entry per grant: role, and the senior for caregiver and senior grants; das first, then medic, caregiver, senior. Whether a warning is active, and the seniors' names, are added with the campaign and senior tables ([auth-layer.md](../auth-layer.md) §3.3) |
````

Replace it with:

````markdown
| My profile | `GET /me` | Any number with a grant | Display name, phone number, and one entry per grant: role, and for caregiver and senior grants the senior, the senior's form of address and the caregiver's relation; das first, then medic, caregiver, senior. Whether a warning is active is added with the campaign tables ([auth-layer.md](../auth-layer.md) §3.3) |
````

Find:

````markdown
| Seniors | `GET /seniors` | Medic: seniors they registered, drafts included. Caregiver: seniors linked to them. Senior: themselves. DAS: seniors submitted or further along | Per senior: name, form of address, enrollment state, code, reason, since when, acknowledged or not, call in progress or not. For caregiver and medic also the watch state. For every role, the home node state and latest room temperature if there is a node **(proposed)** |
````

Replace it with:

````markdown
| Seniors | `GET /seniors?role=` | Medic: seniors they registered, drafts included. Caregiver: seniors linked to them. Senior: themselves. DAS: seniors submitted or further along. The optional `role` narrows the list to one role's reach | Per senior: id, name, form of address, phone number, landline or not, enrollment state; newest first ([seniors-and-enrollment.md](../seniors-and-enrollment.md) §3.3). Added with their features: code, reason, since when, acknowledged or not, call in progress or not; for caregiver and medic the watch state; for every role, the home node state and latest room temperature if there is a node **(proposed)** |
````

Find:

````markdown
| One senior | `GET /seniors/{id}` | Same scoping | Registration details, address and access details, landline or not, caregivers, current code, consent state, latest event location (caregiver and DAS). For caregiver and medic also the watch. For every role, the home node and its latest room reading **(proposed)** |
````

Replace it with:

````markdown
| One senior | `GET /seniors/{id}` | Same scoping | Registration details, address and access details, landline or not, the call window, the medic's name and practice, and the caregivers with relation and phone number; the same for every role. Added with their features: current code, consent state, latest event location (caregiver and DAS); for caregiver and medic the watch; for every role, the home node and its latest room reading **(proposed)** |
````

Find:

````markdown
| Enrollment requests | `GET /enrollments` | DAS | Seniors in `submitted` |
````

Replace it with:

````markdown
| Enrollment requests | `GET /enrollments` | DAS | Seniors in `submitted`, as rows of `GET /seniors`, oldest first |
````

Find:

````markdown
| Staff | `GET /staff` | DAS | DAS employees and medics: name, phone, practice, on duty or not |
````

Replace it with:

````markdown
| Staff | `GET /staff` | DAS | DAS employees and medics, by name: id, name, phone, practice, and their staff roles. On duty or not is added with the hand-over work (P10) |
````

- [ ] **Step 3: `04-interfaces.md`, §2**

Find:

````markdown
| Save senior draft | `POST /seniors`, `PUT /seniors/{id}` | Medic, own senior | Creates or updates a senior in `draft`. A mobile number for the senior creates the senior grant | The senior is past `draft` |
````

Replace it with:

````markdown
| Save senior | `POST /seniors`, `PUT /seniors/{id}` | `POST`: medic. `PUT`: the medic who registered the senior, or DAS for a senior it reaches, in any state | `POST` creates a senior in `draft` from a name, a form of address and a phone number; the rest is optional. `PUT` replaces every registration field. The senior's grant follows the number: made for a mobile, moved when it changes, removed for a landline ([seniors-and-enrollment.md](../seniors-and-enrollment.md) §3.5) | A mobile number that is already another senior's (`phone_taken`). An edit past `draft` that empties the street or the street number (`missing_fields`) |
````

Find:

````markdown
| Add or remove a caregiver | `POST /seniors/{id}/caregivers`, `DELETE /seniors/{id}/caregivers/{userId}` | Medic, own senior | Creates or removes the caregiver grant. On add, sends the notice SMS **(proposed)** | n/a |
````

Replace it with:

````markdown
| Add or remove a caregiver | `POST /seniors/{id}/caregivers`, `DELETE /seniors/{id}/caregivers/{userId}` | The medic who registered the senior, or DAS for a senior it reaches, in any state | Name, relation and a mobile number. Creates or removes the caregiver grant. The notice SMS on add is not built yet **(proposed)** | Add: the number already is this senior's caregiver (`already_done`). Remove: the user is not this senior's caregiver (`not_found`) |
````

Find:

````markdown
| Submit enrollment | `POST /seniors/{id}/submit` | Medic, own senior | `draft` → `submitted` | Not in `draft`, or required fields missing |
````

Replace it with:

````markdown
| Submit enrollment | `POST /seniors/{id}/submit` | Medic, own senior | `draft` → `submitted` | Not in `draft` (`wrong_state`). No street or no street number (`missing_fields`) |
````

Find:

````markdown
| Accept patient | `POST /seniors/{id}/accept` | DAS | `submitted` → `accepted`; queues the welcome call | Not `submitted` |
````

Replace it with:

````markdown
| Accept patient | `POST /seniors/{id}/accept` | DAS | `submitted` → `accepted`. It will queue the welcome call; until that exists it queues nothing | Not `submitted` (`wrong_state`). A draft is outside DAS's reach (`not_found`) |
````

- [ ] **Step 4: `docs/specs/sentinela/01-architecture.md`, §6**

In the table of who grants whom:

Find:

````markdown
| A medic | A senior, and the senior's caregivers | The registration form: the senior's own number, and each caregiver's name, relation and number |
````

Replace it with:

````markdown
| A medic | A senior, and the senior's caregivers | The registration form: the senior's own number, and each caregiver's name, relation and number |
| A DAS employee | Caregivers of a senior that is submitted or further along | The caregiver's name, relation and number ([seniors-and-enrollment.md](../seniors-and-enrollment.md) SE9) |
````

In the paragraph that starts "One place enforces permissions":

Find:

````markdown
A user holds at most one senior grant: when a couple shares one mobile, the second senior has no app role and still receives every call ([auth-layer.md](../auth-layer.md) AL2, AL7, AL8).
````

Replace it with:

````markdown
A user holds at most one senior grant, so one mobile number signs in as one senior: registering a second senior with that mobile is refused, while a landline, which signs nobody in, can be shared ([auth-layer.md](../auth-layer.md) AL2, AL7, AL8; [seniors-and-enrollment.md](../seniors-and-enrollment.md) SE10). The medic who registered a senior, and DAS for a senior it reaches, may edit the registration and its caregivers (SE9).
````

- [ ] **Step 5: `docs/specs/sentinela/02-use-cases.md`, UC-01**

Find:

````markdown
6. The medic submits. The senior moves from `draft` to `submitted`.
````

Replace it with:

````markdown
6. The medic submits. The senior moves from `draft` to `submitted`. A submit needs the street and the street number; caregivers are optional ([seniors-and-enrollment.md](../seniors-and-enrollment.md) SE4).
````

- [ ] **Step 6: `docs/specs/sentinela/05-data-model.md`, §3**

Find:

````markdown
| At most one senior grant per user ([auth-layer.md](../auth-layer.md) AL7) | A unique index over `grant.user_id` limited to rows with role `senior`, added with the seniors migration |
````

Replace it with:

````markdown
| At most one senior grant per user ([auth-layer.md](../auth-layer.md) AL7), so one mobile number signs in as one senior ([seniors-and-enrollment.md](../seniors-and-enrollment.md) SE10) | A unique index over `grant.user_id` limited to rows with role `senior`. Saving a second senior with that mobile is refused with `phone_taken` |
````

- [ ] **Step 7: `docs/specs/auth-layer.md`**

In §2:

Find:

````markdown
| AL7 | At most one `senior` grant per user. When a couple shares one mobile, the second senior has no app role and still receives every call | The rule is recorded now; the seniors migration adds its index |
````

Replace it with:

````markdown
| AL7 | At most one `senior` grant per user. One mobile number signs in as one senior: a second senior with that mobile is refused with `phone_taken`. A landline can be shared | Reworded by [seniors-and-enrollment.md](seniors-and-enrollment.md) SE10. The index is in the tables migration, `741f75a7dbe1` |
````

In §3.3, the example:

Find:

````markdown
    { "role": "das", "senior_id": null },
    { "role": "medic", "senior_id": null }
````

Replace it with:

````markdown
    { "role": "das", "senior_id": null, "senior_form_of_address": null, "relation": null },
    { "role": "medic", "senior_id": null, "senior_form_of_address": null, "relation": null }
````

And its last bullet:

Find:

````markdown
- **Fields that arrive later, each as an optional addition:** `id`, `relation`, `practice`, `warning_active` (with campaigns), the senior's form of address (with seniors).
````

Replace it with:

````markdown
- **Added with the seniors work**, on every grant and `null` where they do not apply: `senior_form_of_address` and `relation` ([seniors-and-enrollment.md](seniors-and-enrollment.md) §3.3).
- **Fields that arrive later, each as an optional addition:** `id`, `practice`, `warning_active` (with campaigns).
````

In §3.6:

Find:

````markdown
No endpoint in this layer takes a senior. These rules are fixed now so that the seniors work does not have to reopen them.
````

Replace it with:

````markdown
No endpoint in this layer takes a senior. These rules were fixed here and are built by the seniors work ([seniors-and-enrollment.md](seniors-and-enrollment.md) §3.1), which adds one: the medic who registered a senior, and DAS for a senior it reaches, may edit the registration and its caregivers (SE9).
````

In §5:

Find:

````markdown
| `+40700000009` | `999999` | nothing: exercises `not_registered` |
````

Replace it with:

````markdown
| `+40700000004` | `444444` | a caregiver (`POST /api/seniors/{id}/caregivers`) |
| `+40700000005` | `555555` | a senior (`POST /api/seniors` with this number) |
| `+40700000009` | `999999` | nothing: exercises `not_registered` |
````

In §10:

Find:

````markdown
| `GET /staff`, on-duty (`users.on_duty`), the dashboard's „Personal” screen | The staff feature (UC-14 UI, P10) |
````

Replace it with:

````markdown
| `GET /staff` and the dashboard's „Personal” screen | Built by [seniors-and-enrollment.md](seniors-and-enrollment.md) |
| On duty: `PUT /staff/on-duty` and the flag in `GET /staff` | The hand-over work (P10) |
````

Find:

````markdown
| The `seniors` table; `seniors.medic_id`; the FK on `grants.senior_id`; the partial unique index for AL7; the senior-scoped helper for §3.6; `/me`'s senior names | The seniors work (UC-01) |
````

Replace it with:

````markdown
| The `seniors` table; `seniors.medic_id`; the FK on `grants.senior_id`; the partial unique index for AL7 | Built with the data model, in migration `741f75a7dbe1` |
| The senior-scoped helper for §3.6; `/me`'s senior names | Built by [seniors-and-enrollment.md](seniors-and-enrollment.md) |
````

- [ ] **Step 8: `docs/specs/seniors-and-enrollment.md`, §12**

Task 4's `test_a_role_refusal_comes_before_the_body` confirmed the first fact.

Find:

````markdown
| FastAPI answers a role refusal before it validates the body (§3.1 order) | A test in slice 1 |
````

Replace it with:

````markdown
| FastAPI answers a role refusal before it validates the body (§3.1 order) | Confirmed by `test_a_role_refusal_comes_before_the_body` in `backend/tests/test_seniors.py` |
````

- [ ] **Step 9: `backend/AGENTS.md`**

In the layout:

Find:

````markdown
│   ├── main.py        FastAPI app; every route on the /api router, docs at /api/docs
````

Replace it with:

````markdown
│   ├── main.py        FastAPI app; the /api router and the routes with no module of their own; docs at /api/docs
````

Find:

````markdown
│   ├── staff.py       granting staff roles, for POST /staff and grant_das.py
````

Replace it with:

````markdown
│   ├── grants.py      the user row behind a grant, shared by staff, senior and caregiver grants
│   ├── staff.py       granting staff roles, for POST /staff and grant_das.py; listing them, for GET /staff
│   ├── reach.py       who reaches which senior, as one SQL condition (auth-layer §3.6)
│   ├── seniors.py     seniors, caregivers and enrollment, on a router included into /api
````

In "Scope":

Find:

````markdown
- Every route goes on the `api` router (prefix `/api`) and must be declared before `app.include_router(api)` at the bottom of `main.py`.
````

Replace it with:

````markdown
- Every route goes on the `api` router (prefix `/api`), or on a module's own router that `main.py` includes into `api`, as `seniors.py` does. Both happen before `app.include_router(api)` at the bottom of `main.py`, which copies the routes it has at that point.
````

- [ ] **Step 10: `backend/README.md`**

In the table of test numbers:

Find:

````markdown
| `+40700000009` | `999999` | nothing |
````

Replace it with:

````markdown
| `+40700000004` | `444444` | a caregiver |
| `+40700000005` | `555555` | a senior |
| `+40700000009` | `999999` | nothing |
````

- [ ] **Step 11: Check the result**

Run, from the repository root: `git diff --stat`
Expected: the eight files above and no others.

Run: `grep -rn "couple shares one mobile" docs/specs/sentinela docs/specs/auth-layer.md`
Expected: no output. The shared-mobile sentence is gone from both places (seniors SE10).

Run: `grep -c "phone_taken" docs/specs/sentinela/04-interfaces.md`
Expected: `2`, the reason in §0 and the save row in §2.

- [ ] **Step 12: Commit**

No Python file is staged, so the hooks run nothing.

```bash
git add docs/specs backend/AGENTS.md backend/README.md
git commit -F - <<'EOF'
docs: bring the spec in line with the seniors backend (seniors §6.6)

04 §0 to §2, 01 §6, UC-01, 05 §3 and auth-layer match the endpoints as
built: the medic or DAS edits in any state, one mobile number signs in as
one senior, /me names the senior, GET /staff returns roles.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 9: Final verification and the real-token check

**Files:** none. This task changes nothing and commits nothing.

**Interfaces:**
- Consumes: everything above; `scripts/grant_das.py` and `scripts/dev_token.py`; the Firebase test numbers of spec §5.
- Produces: the report that spec §6.5 asks for.

- [ ] **Step 1: The whole suite, lint and the migration check**

From `backend/`:

Run: `uv run pytest -q`
Expected: `382 passed`.

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean.

Run: `DATABASE_URL=postgresql://sentinela:sentinela@localhost:5432/sentinela_test uv run alembic check`
Expected: `No new upgrade operations detected.`

- [ ] **Step 2: Start the API from this branch**

From the repository root:

Run: `docker compose up -d --build --wait db api`
Expected: both services healthy or running.

Run: `curl -s localhost:8000/api/health`
Expected: `{"status":"ok","env":"local"}`

- [ ] **Step 3: Grant the staff test numbers**

Run: `docker compose exec api python scripts/grant_das.py "DAS Test" +40700000001`
Expected: `granted`, or `already granted`.

Then make `+40700000002` and `+40700000003` medics. Run this as one command, from the repository root; shell variables do not survive between separate commands:

```bash
cd backend && DAS=$(uv run python scripts/dev_token.py +40700000001 111111) && for medic in '{"display_name": "Medic Test", "phone": "+40700000002", "role": "medic", "practice": "CMI Test"}' '{"display_name": "Alt Medic", "phone": "+40700000003", "role": "medic", "practice": "CMI Alt"}'; do curl -s -w ' -> %{http_code}\n' -H "Authorization: Bearer $DAS" -H "Content-Type: application/json" -d "$medic" localhost:8000/api/staff; done
```

Expected: each line ends `-> 201`, or `-> 409` with `already_done` if the number was a medic already.

`dev_token.py` reads the Firebase web key from `backend/.env` or `dashboard/.env`. If it reports that the key is not set, stop and report that; do not look for the key elsewhere.

- [ ] **Step 4: Run the story of spec §1**

This needs `+40700000004` to be a test number in the Firebase console (spec §5, a person's step). If `dev_token.py` fails for it, **stop and report it**; do not substitute another number.

Run this as one command, from the repository root. Do not save it in the repository.

```bash
bash <<'EOF'
set -eu
cd backend
token() { uv run python scripts/dev_token.py "$1" "$2"; }
send() { # send <token> <method> <path> [json body]: the response body alone
  curl -s -X "$2" -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    ${4:+-d "$4"} "localhost:8000/api$3"
}
status() { # status <token> <method> <path>: the HTTP status alone
  curl -s -o /dev/null -w '%{http_code}' -X "$2" -H "Authorization: Bearer $1" \
    "localhost:8000/api$3"
}
DAS=$(token +40700000001 111111)
MEDIC=$(token +40700000002 222222)
OTHER=$(token +40700000003 333333)
CAREGIVER=$(token +40700000004 444444)

SENIOR=$(send "$MEDIC" POST /seniors '{"full_name": "Maria Popescu", "form_of_address": "doamna Maria", "phone": "0256 123 456", "street": "Str. Daliei", "street_number": "12"}' | jq -r .id)
[ "$SENIOR" != null ] || { echo "the senior was not created"; exit 1; }
ADDED=$(send "$MEDIC" POST "/seniors/$SENIOR/caregivers" '{"display_name": "Ioana Pop", "relation": "fiică", "phone": "+40700000004"}' | jq -r .user_id)
echo "2.  registered $SENIOR, caregiver $ADDED"
echo "4.  another medic reads the draft:    $(status "$OTHER" GET "/seniors/$SENIOR") (want 404)"
echo "5a. DAS reads the draft:              $(status "$DAS" GET "/seniors/$SENIOR") (want 404)"
echo "2.  the medic submits:                $(status "$MEDIC" POST "/seniors/$SENIOR/submit") (want 200)"
echo "3.  the caregiver's grant in /me:     $(send "$CAREGIVER" GET /me | jq -c '.grants[0]')"
echo "3.  the caregiver's list:             $(send "$CAREGIVER" GET /seniors | jq -c '[.[].form_of_address]') (want [\"doamna Maria\"])"
echo "5b. DAS reads her:                    $(status "$DAS" GET "/seniors/$SENIOR") (want 200)"
echo "5b. DAS accepts:                      $(status "$DAS" POST "/seniors/$SENIOR/accept") (want 200)"
echo "5b. DAS accepts again:                $(status "$DAS" POST "/seniors/$SENIOR/accept") (want 409)"
echo "6.  the medic removes the caregiver:  $(status "$MEDIC" DELETE "/seniors/$SENIOR/caregivers/$ADDED") (want 204)"
echo "6.  the caregiver asks again:         $(send "$CAREGIVER" GET /seniors) (want not_registered)"
EOF
```

Expected: every line shows the status it wants. The caregiver's grant in `/me` has `"role":"caregiver"`, `"senior_form_of_address":"doamna Maria"` and `"relation":"fiică"`.

Step 4 of the story is checked while she is still a draft. Locally `+40700000003` is usually DAS as well as a medic (auth-layer §5), and DAS rightly reaches a submitted senior.

Running it twice makes a second senior with the same landline, which is allowed. The second run's caregiver add still answers 201, because the first run removed the grant.

- [ ] **Step 5: Report**

Report, for spec §6.5:
- The three results of Step 1.
- The lines Step 4 printed, or that it stopped and why.
- That nothing was pushed and no pull request was opened. Do either only when the person asks.

Leave the Compose stack as you found it: if you started `api` for this task, stop it with `docker compose stop api`.
