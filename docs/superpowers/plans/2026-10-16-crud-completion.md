# CRUD completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the missing staff, senior, caregiver, consent, call-history and push-token endpoints, update the spec documents to match, and make Android explain `phone_taken`.

**Architecture:** Each endpoint goes into the feature package that owns its table (`staff/`, `seniors/`, `auth/`), plus one new package, `app/calls/`, for the call reads. Rules and queries live in `service.py`, request plumbing in `router.py`, Pydantic in `schemas.py`. No migration: the two new enum members are plain `VARCHAR(32)` values.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async with asyncpg, Postgres 18, pytest with httpx `AsyncClient`; Kotlin and JUnit for the Android task.

**Spec:** [docs/superpowers/specs/2026-10-16-crud-completion-design.md](../specs/2026-10-16-crud-completion-design.md). Read it before Task 1; §4 is the contract, and its tables are the source of every status code and reason below.

## Global Constraints

- Tasks 1–10 go on branch `crud-backend`. Task 11 goes on a new branch `android-phone-taken`, cut from `main`.
- Run backend commands from `backend/`. Postgres must be up: `docker compose up -d db` from the repository root. Tests use the `echocare_test` database, set up by `tests/conftest.py`.
- `backend/AGENTS.md` rules apply:
  - Import a name from the module that defines it. No imports inside functions, and `__init__.py` files stay empty.
  - ORM classes go in `models.py`. Pydantic goes in `schemas.py`: bodies end in `Form`, responses in `View`, `Summary` or `Detail`.
  - `uv run lint-imports` must pass without changing a contract.
- A refusal is `raise refuse(status, reason, **extra)` from `app.auth.service`. Log it first with `log.info("refused <reason>: user %s, senior %s", …)`, as `seniors/service.py` does. When a rollback is needed, log before it ("expires every row, so log first").
- No migration. `tests/core/test_models.py::test_models_match_the_migration` runs `alembic check` and must keep passing.
- Comments are English and cite the spec by ID (`04 §2`, `SE9`, `Q22`), matching the existing density. User-facing Android text is Romanian.
- Commit with the hooks on: lefthook runs ruff, lint-imports and pytest. Never `--no-verify` or `LEFTHOOK=0`. End every commit message with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't push and don't open PRs.
- Test module basenames must be unique across `tests/`: pytest runs without `__init__.py` files. `tests/voice/test_calls.py` already exists.

## Review Focus

1. **Two DAS employees switch the on-duty person at the same moment.** Both get 204, and exactly one person ends up on duty. Neither gets a 500 from the partial unique index. *Test in Task 2.*
2. **A DAS employee removes their own `das` role while another DAS exists.** 204, and their next request is 403 `not_registered`. *Test in Task 2.*
3. **An empty `PATCH` body `{}`.** 200 with nothing changed, for both staff and caregivers. *Tests in Tasks 1 and 5.*
4. **A signature point that isn't a pair** (`[0.1]` or `[0.1, 0.2, 0.3]`). 422 from FastAPI, nothing stored. *Test in Task 7.*
5. **DAS asks for the transcript of a call whose senior is still a `draft`.** 404 `not_found`, because DAS doesn't reach drafts. *Test in Task 8.*

---

### Task 1: Edit a staff member (`PATCH /staff/{user_id}`)

**Files:**
- Modify: `backend/app/staff/schemas.py`, `backend/app/staff/service.py`, `backend/app/staff/router.py`
- Test: `backend/tests/staff/test_staff.py` (append)

**Interfaces:**
- Produces:
  - `STAFF_ROLES = (Role.das, Role.medic)`, moved into `staff/service.py`.
  - `async def staff_listings(session: AsyncSession, user_id: uuid.UUID | None = None) -> list[StaffListingView]`: today's `GET /staff` query and grouping, moved out of the router, optionally narrowed to one user.
  - `class StaffEditForm(BaseModel)`: `display_name: Name | None = None`, `practice: Practice | None = None`. `None` means unchanged.
  - `async def edit_staff(session: AsyncSession, user_id: uuid.UUID, form: StaffEditForm) -> StaffListingView`.

- [ ] **Step 1: Write the failing tests** (append to `tests/staff/test_staff.py`; `das` fixture, `post`, `signed_in` already there)

```python
async def patch_staff(client, user_id, body, token=DAS):
    return await client.patch(f"/api/staff/{user_id}", json=body, headers=signed_in(token))

async def test_das_edits_a_medic(client, db, das):
    medic = (await post(client, MEDIC)).json()
    user = await db.scalar(select(User).where(User.phone_e164 == medic["phone_e164"]))
    r = await patch_staff(client, user.id, {"display_name": "Dr. Ion Popescu", "practice": "CMI Nou", "phone": "0700 000 099"})
    assert r.status_code == 200
    assert r.json() == {"id": str(user.id), "display_name": "Dr. Ion Popescu", "phone_e164": medic["phone_e164"],
                        "practice": "CMI Nou", "roles": ["medic"], "on_duty": False}  # the phone stays (Q8)

async def test_an_empty_patch_changes_nothing(client, das):   # Review Focus 3
    r = await patch_staff(client, das.id, {})
    assert (r.status_code, r.json()["display_name"]) == (200, "DAS Test")

async def test_practice_needs_a_medic(client, das):
    r = await patch_staff(client, das.id, {"practice": "CMI"})
    assert (r.status_code, r.json()) == (422, {"detail": {"reason": "not_medic"}})

async def test_only_staff_can_be_edited(client, add_user, das):
    nobody = await add_user("+40700000004")  # a user row without a das or medic grant
    for user_id in (nobody.id, uuid.uuid4()):
        r = await patch_staff(client, user_id, {"display_name": "X"})
        assert (r.status_code, r.json()) == (404, {"detail": {"reason": "not_found"}})

async def test_a_medic_cannot_edit_staff(client, add_user, das):
    await add_user("+40700000003", Role.medic)
    r = await patch_staff(client, das.id, {"display_name": "X"}, token="+40700000003")
    assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_allowed"}})
```

Add `import uuid` at the top of the module.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/staff/test_staff.py -q`
Expected: the five new tests FAIL (405 Method Not Allowed); the existing tests PASS.

- [ ] **Step 3: Move the listing into `staff/service.py` and add `edit_staff`**

`list_staff` in the router becomes `return await staff_listings(session)`. `edit_staff`:
- loads the user's grants in `STAFF_ROLES`; none is `refuse(404, "not_found")`;
- `form.practice is not None` without `Role.medic` is `refuse(422, "not_medic")`;
- sets each non-`None` field on the `User`, commits, and returns `(await staff_listings(session, user_id))[0]`.

Route: `PATCH /staff/{user_id}`, `require_roles(Role.das)`. The docstring cites `04 §2` and Q8.

- [ ] **Step 4: Run the staff tests**

Run: `uv run pytest tests/staff -q`
Expected: all PASS, including the existing `test_the_staff_list`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/staff backend/tests/staff/test_staff.py
git commit -m "feat(staff): PATCH /staff/{user_id} edits name and practice"
```

---

### Task 2: Remove a staff role, and on duty

**Files:**
- Modify: `backend/app/staff/schemas.py`, `backend/app/staff/service.py`, `backend/app/staff/router.py`
- Test: `backend/tests/staff/test_staff.py` (append)

**Interfaces:**
- Consumes: `staff_listings` (Task 1).
- Produces:
  - `STAFF_LOCK: int`, one fixed key for `pg_advisory_xact_lock`.
  - `async def revoke_staff(session: AsyncSession, user_id: uuid.UUID, role: Role) -> None`.
  - `class OnDutyForm(BaseModel)`: `user_id: uuid.UUID`.
  - `async def set_on_duty(session: AsyncSession, user_id: uuid.UUID | None) -> None`, where `None` clears.

- [ ] **Step 1: Write the failing tests**

```python
async def listed(client):
    return {s["phone_e164"]: s for s in (await client.get("/api/staff", headers=signed_in(DAS))).json()}

async def test_removing_a_medic_role(client, db, das, add_user):
    medic = await add_user("+40700000002", Role.medic)
    path = f"/api/staff/{medic.id}/roles/medic"
    assert (await client.delete(path, headers=signed_in(DAS))).status_code == 204
    assert (await client.delete(path, headers=signed_in(DAS))).status_code == 204  # a repeat
    assert "+40700000002" not in await listed(client)

async def test_removing_das_takes_them_off_duty(client, db, das, add_user):
    other = await add_user("+40700000003", Role.das)
    other.on_duty = True; await db.commit()
    r = await client.delete(f"/api/staff/{other.id}/roles/das", headers=signed_in(DAS))
    assert r.status_code == 204
    await db.refresh(other)
    assert other.on_duty is False

async def test_the_last_das_stays(client, db, das):
    r = await client.delete(f"/api/staff/{das.id}/roles/das", headers=signed_in(DAS))
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})
    assert await db.scalar(select(Grant).where(Grant.user_id == das.id)) is not None

async def test_removing_your_own_das_role(client, das, add_user):   # Review Focus 2
    await add_user("+40700000003", Role.das)
    assert (await client.delete(f"/api/staff/{das.id}/roles/das", headers=signed_in(DAS))).status_code == 204
    r = await client.get("/api/profile", headers=signed_in(DAS))
    assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_registered"}})

async def test_only_staff_roles_are_removed_here(client, das):
    r = await client.delete(f"/api/staff/{das.id}/roles/caregiver", headers=signed_in(DAS))
    assert r.status_code == 422

async def test_on_duty_switches(client, das, add_user):
    other = await add_user("+40700000003", Role.das)
    for user, phone in ((das, DAS), (other, "+40700000003")):
        r = await client.put("/api/staff/on-duty", json={"user_id": str(user.id)}, headers=signed_in(DAS))
        assert r.status_code == 204
        assert [p for p, s in (await listed(client)).items() if s["on_duty"]] == [phone]
    assert (await client.delete("/api/staff/on-duty", headers=signed_in(DAS))).status_code == 204
    assert not any(s["on_duty"] for s in (await listed(client)).values())

async def test_on_duty_needs_a_das(client, das, add_user):
    medic = await add_user("+40700000002", Role.medic)
    r = await client.put("/api/staff/on-duty", json={"user_id": str(medic.id)}, headers=signed_in(DAS))
    assert (r.status_code, r.json()) == (403, {"detail": {"reason": "not_allowed"}})

async def test_two_on_duty_switches_at_once(client, das, add_user):   # Review Focus 1
    other = await add_user("+40700000003", Role.das)
    rs = await asyncio.gather(*(
        client.put("/api/staff/on-duty", json={"user_id": str(u.id)}, headers=signed_in(DAS)) for u in (das, other)
    ))
    assert [r.status_code for r in rs] == [204, 204]
    assert sum(s["on_duty"] for s in (await listed(client)).values()) == 1

@pytest.mark.parametrize("method", ["delete_role", "put_on_duty", "delete_on_duty"])
async def test_staff_changes_are_for_das(client, add_user, das, method):
    await add_user("+40700000002", Role.medic)
    # each request sent with token "+40700000002" → 403 not_allowed
```

Fill in the last test's three requests; each must answer `(403, {"detail": {"reason": "not_allowed"}})`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/staff/test_staff.py -q`
Expected: the new tests FAIL (404 or 405).

- [ ] **Step 3: Implement**

`revoke_staff` and `set_on_duty` each start with `await session.execute(select(func.pg_advisory_xact_lock(STAFF_LOCK)))` (spec §5.3).

`revoke_staff`:
- For `Role.das`, count the `das` grants. If the user holds `das` and the count is 1, refuse with 409 `wrong_state`.
- Delete the grant. For `das`, also set the user's `on_duty = False`.
- Commit.

`set_on_duty`:
- A `user_id` without a `das` grant: refuse with 403 `not_allowed`.
- Set `on_duty = False` on every row where it's true, flush, then set the target's to true.
- Commit.

Routes, all `require_roles(Role.das)` and `status_code=204`:
- `DELETE /staff/{user_id}/roles/{role}`, with `role: Literal["das", "medic"]` as a path parameter.
- `PUT /staff/on-duty`, with body `OnDutyForm`.
- `DELETE /staff/on-duty`.

- [ ] **Step 4: Run the staff tests**

Run: `uv run pytest tests/staff -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/staff backend/tests/staff/test_staff.py
git commit -m "feat(staff): remove a staff role, set and clear on duty"
```

---

### Task 3: The medic or DAS edits a senior in any state (SE9)

**Files:**
- Modify: `backend/app/seniors/service.py`, `backend/app/seniors/router.py`
- Test: `backend/tests/seniors/test_seniors.py` (update four tests, append two)

**Interfaces:**
- Produces: `async def editable_senior(session: AsyncSession, caller: Caller, senior_id: uuid.UUID) -> Senior`. It calls `reach_senior(…, lock=True)` and allows the registering medic (holds `medic` and `senior.medic_id == caller.user.id`) or anyone holding `das`; otherwise 403 `not_allowed`.

- [ ] **Step 1: Update the tests that pin the old rule, and add the new ones**

Existing tests whose assertions change:
- `test_das_sees_a_senior_once_submitted`: DAS's `PUT` now answers 200.
- `test_the_medic_edits_a_draft_or_a_request`: rename it `test_the_medic_edits_in_any_state`.
  - In `accepted` the `PUT` answers 200.
  - In `accepted`, a body with `"street": ""` answers 422 `incomplete` with `missing: ["street"]`.
- `test_another_medic_who_is_also_das`: she holds `das`, so `PUT`, add caregiver and remove caregiver now succeed (200, 201, 204). `submit` stays `NOT_ALLOWED`. Rename it `test_another_medic_who_is_also_das_edits_as_das`.

New:

```python
async def test_das_edits_an_active_senior(client, db, staff):
    maria = await register(client)
    await add_caregiver(client, maria["id"])
    await set_state(db, maria["id"], EnrollmentState.active)
    path = f"/api/seniors/{maria['id']}"
    r = await client.put(path, json={**MARIA, "landmark": "lângă farmacie"}, headers=signed_in(DAS))
    assert (r.status_code, r.json()["landmark"]) == (200, "lângă farmacie")
    ion = await add_caregiver(client, maria["id"], {**ANA, "display_name": "Ion", "phone": "0700 000 007"}, DAS)
    assert ion.status_code == 201
    r = await client.delete(f"{path}/caregivers/{ion.json()['user_id']}", headers=signed_in(DAS))
    assert r.status_code == 204

async def test_das_does_not_reach_a_draft(client, staff):
    maria = await register(client)
    r = await client.put(f"/api/seniors/{maria['id']}", json=MARIA, headers=signed_in(DAS))
    assert refusal(r) == NOT_FOUND
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/seniors/test_seniors.py -q`
Expected: the changed and new tests FAIL with 403 or 409.

- [ ] **Step 3: Implement**

- Add `editable_senior` next to `own_senior`.
- `edit`, `grant_caregiver` and `revoke_caregiver` call `editable_senior` instead of `own_senior`.
- `edit` drops its state refusal. Its `incomplete` check now applies whenever `senior.enrollment_state != EnrollmentState.draft`.
- In the router, `PUT /seniors/{id}`, `POST …/caregivers` and `DELETE …/caregivers/{user_id}` use `require_roles(Role.medic, Role.das)`. Update their docstrings (SE9).
- `own_senior` keeps serving `submit`.

- [ ] **Step 4: Run the seniors tests**

Run: `uv run pytest tests/seniors -q`
Expected: all PASS, including `test_others_cannot_change_a_senior` unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seniors backend/tests/seniors/test_seniors.py
git commit -m "feat(seniors): the medic or DAS edits a senior in any state (SE9)"
```

---

### Task 4: `phone_taken` (SE10)

**Files:**
- Modify: `backend/app/seniors/service.py`
- Test: `backend/tests/seniors/test_seniors.py`

**Interfaces:**
- Consumes: `editable_senior` (Task 3).
- Produces: `async def sync_senior_grant(session: AsyncSession, senior: Senior) -> bool`. It returns `True` for a landline, or when the senior holds its number's senior grant after the insert. It returns `False` when the number belongs to another senior. `scripts/seed.py` keeps calling it and ignores the result.

- [ ] **Step 1: Write the failing tests**

Replace `test_a_couple_sharing_a_mobile` with:

```python
PHONE_TAKEN = (409, {"detail": {"reason": "phone_taken"}})

async def test_one_mobile_one_senior(client, db, staff):
    await register(client)
    r = await client.post("/api/seniors", json={**MARIA, "full_name": "Ion Pop", "form_of_address": "domnul Ion"},
                          headers=signed_in(MEDIC))
    assert refusal(r) == PHONE_TAKEN
    assert await db.scalar(select(func.count()).select_from(Senior)) == 1  # nothing stored

async def test_an_edit_to_another_seniors_mobile(client, staff):
    await register(client)
    ion = await register(client, {**MARIA, "full_name": "Ion Pop", "phone": "0700 000 008"})
    r = await client.put(f"/api/seniors/{ion['id']}", json=MARIA, headers=signed_in(MEDIC))
    assert refusal(r) == PHONE_TAKEN
    r = await get(client, f"/api/seniors/{ion['id']}", MEDIC)
    assert r.json()["phone_e164"] == "+40700000008"

async def test_a_shared_mobile_from_before_stays_editable(client, add_senior, staff):
    await register(client)
    ion = await add_senior(SENIOR, name="Ion Pop", medic=staff)   # no grant, as AL7 left it
    r = await client.put(f"/api/seniors/{ion.id}", json={**MARIA, "full_name": "Ion Pop", "street": "Str. Nouă"},
                         headers=signed_in(MEDIC))
    assert (r.status_code, r.json()["street"]) == (200, "Str. Nouă")

async def test_a_landline_can_be_shared(client, staff):
    await register(client, {**MARIA, "phone": "0256 123 456"})
    await register(client, {**MARIA, "full_name": "Ion Pop", "phone": "0256 123 456"})  # asserts 201
```

Add `func` to the module's `sqlalchemy` import.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/seniors/test_seniors.py -q`
Expected: the new tests FAIL (201 or 200 instead of 409). `test_a_put_and_an_add_with_the_same_new_number` still PASSES.

- [ ] **Step 3: Implement**

- `sync_senior_grant` keeps its `ON CONFLICT DO NOTHING` insert. It then returns whether a senior grant exists for `(user.id, senior.id)`.
- `register`: when that returns `False`, roll back and refuse with 409 `phone_taken`.
- `edit`: remember `senior.phone_e164` before the update. Refuse the same way only when the result is `False` **and** `form.phone` differs from it.
- Update `sync_senior_grant`'s docstring: SE10 replaces the AL7 sentence.
- `scripts/seed.py` needs no change. Check that `uv run pytest tests/tooling -q` passes.

- [ ] **Step 4: Run the seniors and tooling tests**

Run: `uv run pytest tests/seniors tests/tooling -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seniors backend/tests/seniors/test_seniors.py
git commit -m "feat(seniors): one mobile, one senior: phone_taken (SE10)"
```

---

### Task 5: Edit a caregiver (`PATCH /seniors/{id}/caregivers/{user_id}`)

**Files:**
- Modify: `backend/app/seniors/schemas.py`, `backend/app/seniors/service.py`, `backend/app/seniors/router.py`
- Test: `backend/tests/seniors/test_seniors.py` (append)

**Interfaces:**
- Consumes: `editable_senior` (Task 3).
- Produces:
  - `class CaregiverEditForm(BaseModel)`: `display_name: text(120, 1) | None = None`, `relation: text(60, 1) | None = None`.
  - `async def edit_caregiver(session, caller, senior_id: uuid.UUID, user_id: uuid.UUID, form: CaregiverEditForm) -> CaregiverView`.

- [ ] **Step 1: Write the failing tests**

```python
async def patch_caregiver(client, senior_id, user_id, body, token=MEDIC):
    return await client.patch(f"/api/seniors/{senior_id}/caregivers/{user_id}", json=body, headers=signed_in(token))

async def test_the_medic_edits_a_caregiver(client, staff):
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    r = await patch_caregiver(client, maria["id"], ana["user_id"], {"display_name": "Ana Ionescu", "relation": "nora"})
    assert r.json() == {**ana, "display_name": "Ana Ionescu", "relation": "nora"}
    assert (await get(client, "/api/profile", CAREGIVER)).json()["display_name"] == "Ana Ionescu"  # everywhere (Q13)

async def test_an_empty_caregiver_patch(client, staff):   # Review Focus 3
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    r = await patch_caregiver(client, maria["id"], ana["user_id"], {})
    assert (r.status_code, r.json()) == (200, ana)

async def test_a_staff_caregiver_keeps_their_name(client, staff):   # Q22
    maria = await register(client)
    dr = (await add_caregiver(client, maria["id"], {**ANA, "phone": OTHER_MEDIC})).json()
    r = await patch_caregiver(client, maria["id"], dr["user_id"], {"display_name": "X"})
    assert refusal(r) == NOT_ALLOWED
    r = await patch_caregiver(client, maria["id"], dr["user_id"], {"relation": "vecin"})
    assert (r.status_code, r.json()["display_name"], r.json()["relation"]) == (200, "Dr. Alt", "vecin")

async def test_patching_someone_who_is_not_her_caregiver(client, staff):
    maria = await register(client)
    r = await patch_caregiver(client, maria["id"], staff.id, {"relation": "x"})
    assert refusal(r) == NOT_FOUND

async def test_das_edits_a_caregiver(client, db, staff):
    maria = await register(client)
    ana = (await add_caregiver(client, maria["id"])).json()
    await set_state(db, maria["id"], EnrollmentState.submitted)
    r = await patch_caregiver(client, maria["id"], ana["user_id"], {"relation": "nora"}, DAS)
    assert r.status_code == 200
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/seniors/test_seniors.py -q -k caregiver`
Expected: the new tests FAIL (405).

- [ ] **Step 3: Implement**

`edit_caregiver`:
1. `editable_senior`.
2. Load the caregiver `Grant` for `(senior_id, user_id)`. None is 404 `not_found`.
3. If `display_name` is given and the user holds a `das` or `medic` grant, refuse with 403 `not_allowed`. Do this before changing anything.
4. Set the fields that aren't `None`, commit, and return `CaregiverView`.

Route: `PATCH /seniors/{senior_id}/caregivers/{user_id}`, `require_roles(Role.medic, Role.das)`.

- [ ] **Step 4: Run the seniors tests**

Run: `uv run pytest tests/seniors -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seniors backend/tests/seniors/test_seniors.py
git commit -m "feat(seniors): PATCH a caregiver's relation and name (Q13, Q22)"
```

---

### Task 6: Delete a draft (`DELETE /seniors/{id}`)

**Files:**
- Modify: `backend/app/seniors/service.py`, `backend/app/seniors/router.py`
- Test: `backend/tests/seniors/test_seniors.py` (append)

**Interfaces:**
- Produces: `async def delete_draft(session: AsyncSession, caller: Caller, senior_id: uuid.UUID) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_the_medic_deletes_a_draft(client, db, staff):
    maria = await register(client)
    await add_caregiver(client, maria["id"])
    db.add(Consent(senior_id=maria["id"], decision="given", method="signature", text_version="v1",
                   signature_strokes=[[[0.1, 0.2]]], recorded_by=staff.id))
    await db.commit()
    path = f"/api/seniors/{maria['id']}"
    assert (await client.delete(path, headers=signed_in(MEDIC))).status_code == 204
    assert refusal(await get(client, path, MEDIC)) == NOT_FOUND
    assert await db.scalar(select(Grant).where(Grant.senior_id == maria["id"])) is None
    assert await db.scalar(select(User).where(User.phone_e164 == CAREGIVER)) is not None  # the person stays
    assert refusal(await client.delete(path, headers=signed_in(MEDIC))) == NOT_FOUND     # a repeat

async def test_only_a_draft_is_deleted(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.submitted)
    r = await client.delete(f"/api/seniors/{maria['id']}", headers=signed_in(MEDIC))
    assert refusal(r) == (409, {"detail": {"reason": "wrong_state"}})

async def test_a_draft_with_a_call_stays(client, db, staff):
    maria = await register(client)
    db.add(Call(senior_id=maria["id"], trigger="test", starting_severity="green",
                due_at=datetime.now(UTC), state="completed"))
    await db.commit()
    r = await client.delete(f"/api/seniors/{maria['id']}", headers=signed_in(MEDIC))
    assert refusal(r) == (409, {"detail": {"reason": "wrong_state"}})
    assert (await get(client, f"/api/seniors/{maria['id']}", MEDIC)).status_code == 200

@pytest.mark.parametrize("token", [OTHER_MEDIC, DAS, CAREGIVER])
async def test_others_cannot_delete(client, db, staff, token):
    maria = await register(client)
    await add_caregiver(client, maria["id"])
    r = await client.delete(f"/api/seniors/{maria['id']}", headers=signed_in(token))
    assert refusal(r) == (NOT_FOUND if token == OTHER_MEDIC else NOT_ALLOWED)
```

Import `Call` and `Consent` from `app.models`, and `datetime` and `UTC` from `datetime`. `maria["id"]` is a string: wrap it in `uuid.UUID(...)` when building an ORM row, here and in Task 7.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/seniors/test_seniors.py -q -k delete`
Expected: FAIL (405).

- [ ] **Step 3: Implement**

`delete_draft`:
1. `own_senior`.
2. Not `draft` is 409 `wrong_state`.
3. Execute `delete(Consent).where(Consent.senior_id == senior_id)`, then `delete(Senior).where(Senior.id == senior_id)`, then commit, all inside `try/except IntegrityError`. The `except` branch logs, rolls back and refuses with 409 `wrong_state` (spec §5.4).

Don't import anything from `app.voice`.

Route: `DELETE /seniors/{senior_id}`, `require_roles(Role.medic)`, 204.

- [ ] **Step 4: Run the seniors tests**

Run: `uv run pytest tests/seniors -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seniors backend/tests/seniors/test_seniors.py
git commit -m "feat(seniors): DELETE a draft senior (Q10)"
```

---

### Task 7: Withdrawn consent and the signature

**Files:**
- Modify: `backend/app/seniors/models.py`, `backend/app/seniors/schemas.py`, `backend/app/seniors/service.py`, `backend/app/seniors/router.py`
- Test: `backend/tests/seniors/test_consents.py` (create; copy the few helpers it needs from `test_seniors.py`, since a test module can't import another)

**Interfaces:**
- Consumes: `editable_senior`, `own_senior`, `move`.
- Produces:
  - `EnrollmentState.withdrawn = "withdrawn"` and `ConsentMethod.das = "das"`.
  - `MAX_SIGNATURE_POINTS = 5000`.
  - `class SignatureForm(BaseModel)`:
    - `text_version: text(40, 1)`;
    - `strokes: list[list[tuple[Coordinate, Coordinate]]]`, where `Coordinate = Annotated[float, Field(ge=0, le=1)]`;
    - `min_length=1` on both lists;
    - a model validator that refuses more than `MAX_SIGNATURE_POINTS` points in total.
  - `async def withdraw_consent(session, caller, senior_id) -> SeniorSummary`.
  - `async def save_signature(session, caller, senior_id, form: SignatureForm) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_the_medic_records_a_withdrawal(client, db, staff):
    maria = await register(client)
    await set_state(db, maria["id"], EnrollmentState.active)
    db.add(Consent(senior_id=maria["id"], decision="given", method="call", text_version="v1"))
    await db.commit()
    r = await client.post(f"/api/seniors/{maria['id']}/consent-withdrawn", headers=signed_in(MEDIC))
    assert (r.status_code, r.json()["enrollment_state"]) == (200, "withdrawn")
    latest = await db.scalar(select(Consent).where(Consent.senior_id == maria["id"]).order_by(Consent.at.desc()).limit(1))
    assert (latest.decision, latest.method, latest.text_version, latest.recorded_by) == ("withdrawn", "medic", "v1", staff.id)
    r = await client.post(f"/api/seniors/{maria['id']}/consent-withdrawn", headers=signed_in(MEDIC))
    assert refusal(r) == (409, {"detail": {"reason": "already_done"}})

async def test_das_records_a_withdrawal(client, db, staff):
    # active, no consent row → method "das", text_version "none"

async def test_a_withdrawal_needs_an_active_senior(client, db, staff):
    # submitted → 409 wrong_state, and no consent row was added

async def test_a_caregiver_cannot_withdraw(client, db, staff):
    # caregiver token → NOT_ALLOWED

STROKES = [[[0.1, 0.2], [0.3, 0.4]]]

async def test_the_medic_saves_a_signature(client, db, staff):
    maria = await register(client)
    r = await client.post(f"/api/seniors/{maria['id']}/signature",
                          json={"text_version": "v1", "strokes": STROKES}, headers=signed_in(MEDIC))
    assert r.status_code == 204
    row = await db.scalar(select(Consent).where(Consent.senior_id == maria["id"]))
    assert (row.decision, row.method, row.signature_strokes, row.recorded_by) == ("given", "signature", STROKES, staff.id)

async def test_no_signature_once_active(client, db, staff):
    # active → 409 wrong_state

@pytest.mark.parametrize("strokes", [
    [], [[]], [[[1.5, 0.2]]], [[[0.1]]], [[[0.1, 0.2, 0.3]]],   # the last two: Review Focus 4
    [[[0.5, 0.5]] * 5001],
])
async def test_invalid_signatures(client, staff, strokes):
    # → 422, and no consent row

async def test_das_cannot_sign(client, db, staff):
    # submitted, DAS token → NOT_ALLOWED
```

The bodies marked with `#` are one request and one assertion each, as their comment says.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/seniors/test_consents.py -q`
Expected: FAIL (404 or 405).

- [ ] **Step 3: Implement**

`withdraw_consent`:
1. `editable_senior`.
2. Read the latest `Consent.text_version` by `at` desc, then `id` desc.
3. `session.add(Consent(decision=withdrawn, method=medic if the caller is the registering medic else das, text_version=latest or "none", recorded_by=caller.user.id))`.
4. `await move(session, caller, senior, EnrollmentState.active, EnrollmentState.withdrawn)`.

`move` commits both rows. A refusal leaves the consent uncommitted, and the request's session drops it. Return `SeniorSummary`.

`save_signature`:
1. `own_senior`.
2. A state outside `{draft, submitted, accepted}` is 409 `wrong_state`.
3. Add `Consent(decision=given, method=signature, text_version, signature_strokes=<strokes as nested lists>, recorded_by)` and commit.

Routes:
- `POST /seniors/{id}/consent-withdrawn`: `require_roles(Role.medic, Role.das)`, answers `SeniorSummary`.
- `POST /seniors/{id}/signature`: `require_roles(Role.medic)`, 204.

- [ ] **Step 4: Run the backend suite**

Run: `uv run pytest -q`
Expected: all PASS, including `test_models_match_the_migration`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seniors backend/tests/seniors/test_consents.py
git commit -m "feat(seniors): consent-withdrawn and signature (Q15, Q16)"
```

---

### Task 8: Call history and transcripts (`app/calls/`)

**Files:**
- Create: `backend/app/calls/__init__.py` (empty), `backend/app/calls/schemas.py`, `backend/app/calls/service.py`, `backend/app/calls/router.py`
- Modify: `backend/app/main.py` (include `calls_router` after `incidents_router`)
- Test: `backend/tests/calls/test_call_history.py` (create)

**Interfaces:**
- Consumes:
  - `reach`, `reach_senior` from `app.seniors.service`;
  - `CallDetail`, `TurnView`, `ReportView`, `Level` from `app.incidents.schemas`;
  - `call_detail` from `app.incidents.service`;
  - `Call`, `CallTurn`, `Answer`, `StatusReport`, `CallTrigger` from `app.voice.models`.
- Produces:
  - `class CallSummary(BaseModel)`: `id`, `trigger: str`, `state: str`, `due_at`, `started_at`, `ended_at`, `final_severity: Level | None`, `final_certainty: Level | None`, `reason`, `summary`.
  - `class AnswerView(BaseModel)`: `field: str`, `value: str`, `clear: bool`, `quote: str`, `at: datetime`.
  - `class TranscriptDetail(CallDetail)`: `answers: list[AnswerView]`.
  - `async def call_history(session, caller, senior_id) -> list[CallSummary]`.
  - `async def transcript(session, caller, call_id) -> TranscriptDetail`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_everyone_who_reaches_her_sees_her_calls(client, db, people):
    # people: DAS, MEDIC (registers maria, past draft), CAREGIVER, SENIOR; three calls: two "watch" a day apart, one "test"
    for token in (DAS, MEDIC, CAREGIVER, SENIOR):
        r = await client.get(f"/api/seniors/{maria_id}/calls", headers=signed_in(token))
        assert [c["id"] for c in r.json()] == [newer_id, older_id]   # newest first, test call left out
    assert r.json()[0]["final_severity"] == "red"

async def test_someone_else_does_not_see_her_calls(client, people):  # stranger medic → 404 not_found

async def test_the_transcript(client, db, people):
    # one call with two CallTurn rows (positions 1, 2), one StatusReport, one Answer(field="feeling", value="ok", clear=True, quote="bine")
    r = await client.get(f"/api/calls/{call_id}/transcript", headers=signed_in(MEDIC))
    body = r.json()
    assert [t["content"] for t in body["turns"]] == ["Cum vă simțiți?", "bine"]
    assert body["answers"] == [{"field": "feeling", "value": "ok", "clear": True, "quote": "bine", "at": ANY}]
    assert (await client.get(..., headers=signed_in(DAS))).status_code == 200

@pytest.mark.parametrize("token", [CAREGIVER, SENIOR, OTHER_MEDIC])
async def test_the_transcript_is_for_her_medic_and_das(client, people, token):  # → 404 not_found

async def test_das_does_not_see_a_drafts_transcript(client, db, people):   # Review Focus 5
    # maria back to draft → DAS gets 404 not_found, MEDIC still 200
```

Build the `people` fixture from `add_user`, `add_senior` and direct `Grant` and `Call` inserts, the way `tests/incidents/test_incident_view.py` does. Use `ANY` from `unittest.mock` for the timestamp.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/calls -q`
Expected: FAIL (404 from routing).

- [ ] **Step 3: Implement**

`call_history`:
1. `reach_senior(session, caller, senior_id)`.
2. Select calls with `Call.senior_id == senior_id` and `Call.trigger != CallTrigger.test`, ordered by `created_at` desc, then `id` desc.

`transcript`:
1. Select the `Call` joined to `Senior`, where `Call.id == call_id` and `or_(reach(caller, Role.medic), reach(caller, Role.das))`. None is 404 `not_found`.
2. Load turns by `position`, reports by `at` and answers by `at`.
3. Build `call_detail(call, reports, turns)`, and return `TranscriptDetail(**detail.model_dump(), answers=…)`.

Routes, each depending on `current_caller`:
- `GET /seniors/{senior_id}/calls`
- `GET /calls/{call_id}/transcript`

- [ ] **Step 4: Run the suite and the import contracts**

Run: `uv run pytest -q && uv run lint-imports`
Expected: all PASS, and the contracts are kept (including `test_contracts.py`, which checks the new empty `__init__.py`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/calls backend/app/main.py backend/tests/calls
git commit -m "feat(calls): GET /seniors/{id}/calls and GET /calls/{id}/transcript"
```

---

### Task 9: Push tokens (`/profile/push-tokens/{token}`)

**Files:**
- Modify: `backend/app/auth/service.py`, `backend/app/auth/router.py`
- Test: `backend/tests/auth/test_push_tokens.py` (create)

**Interfaces:**
- Produces:
  - `async def save_push_token(session: AsyncSession, caller: Caller, token: str) -> None`: `insert(PushToken).on_conflict_do_update(index_elements=[PushToken.token], set_={"user_id": caller.user.id, "updated_at": func.now()})`.
  - `async def drop_push_token(session: AsyncSession, caller: Caller, token: str) -> None`: deletes only where `user_id == caller.user.id`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_save_and_repeat(client, db, add_user)        # PUT twice → 204, 204; one row, the caller's
async def test_a_token_moves_to_whoever_signs_in(client, db, add_user)  # user B PUTs A's token → one row, B's
async def test_only_your_own_token_is_dropped(client, db, add_user)    # B DELETEs A's token → 204, row stays; A DELETEs → 204, gone; again → 204
async def test_a_token_too_long(client, add_user)            # "x" * 513 → 422
async def test_signed_out_and_unknown(client)                # no token → 401 not_signed_in; "+40700000009" → 403 not_registered
```

Each comment states the requests and the assertions. The path is `/api/profile/push-tokens/{token}`. Use a realistic token such as `"fcm:abc-123_DEF"`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/auth/test_push_tokens.py -q`
Expected: FAIL (404 or 405).

- [ ] **Step 3: Implement**

Routes `PUT` and `DELETE /profile/push-tokens/{token}`, with `token: Annotated[str, Path(max_length=512)]`, `Depends(current_caller)`, status 204. The docstring cites G4 and Q19.

- [ ] **Step 4: Run the auth tests**

Run: `uv run pytest tests/auth -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth backend/tests/auth/test_push_tokens.py
git commit -m "feat(auth): save and drop push tokens under /profile (Q19)"
```

---

### Task 10: Spec documents

**Files:**
- Modify: `docs/specs/echocare/04-interfaces.md`, `docs/specs/echocare/05-data-model.md`, `docs/specs/seniors-and-enrollment.md`, `docs/specs/auth-layer.md`, `docs/specs/echocare/01-architecture.md`, `docs/specs/echocare/02-use-cases.md`

**Interfaces:**
- Consumes: the endpoints exactly as built in Tasks 1–9.

- [ ] **Step 1: Make each change in the CRUD spec's §7 table**

`04 §2` gets one row per new endpoint, in the existing column order (Request, Indicative address, Who, Effect, Refused when). The changed rows (Save senior draft, Add or remove a caregiver, Save signature, Record withdrawal, Save push token, Set on duty) are rewritten to match spec §4. Mark nothing "(proposed)" that is now built.

- [ ] **Step 2: Find every other list of enrollment states and add `withdrawn`**

Run: `grep -rn "wrong_number" docs/specs`
Expected: each hit that lists the states now also lists `withdrawn`.

- [ ] **Step 3: Check that nothing still says the old rules**

Run: `grep -rn -E "/me/push-tokens|only the medic who registered|a second senior on one mobile gets no grant" docs/specs`
Expected: no hits, except deliberate history: the earlier v3 spec and `unihack.md`.

- [ ] **Step 4: Commit**

```bash
git add docs/specs
git commit -m "docs(spec): 04, 05, SE, AL and UC match the CRUD endpoints"
```

---

### Task 11: Android explains `phone_taken` (branch `android-phone-taken`)

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/enroll/Refusal.kt`, `android/app/src/main/res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/enroll/RefusalTest.kt`

**Interfaces:**
- Produces: `Refusal.PhoneTaken`, a `data object`, and string resource `phone_taken` = „Acest număr este deja al altui senior.”

- [ ] **Step 1: Cut the branch**

Run: `git switch -c android-phone-taken main`
Expected: `Switched to a new branch 'android-phone-taken'`.

- [ ] **Step 2: Write the failing tests** (in `RefusalTest`)

```kotlin
@Test
fun phoneTakenMarksThePhone() {
    val body = """{"detail": {"reason": "phone_taken"}}"""
    assertEquals(Refusal.PhoneTaken, refusalOf(409, body))
    assertEquals(Then.Mark(mapOf(Field.Phone to R.string.phone_taken)), thenAfter(Action.Save, Refusal.PhoneTaken))
}
```

- [ ] **Step 3: Run it and see it fail**

Run (from `android/`): `./gradlew :app:testDebugUnitTest --tests ro.echocare.enroll.RefusalTest`
Expected: compilation fails because `PhoneTaken` is undefined.

- [ ] **Step 4: Implement**

- Add `data object PhoneTaken : Refusal` with a KDoc citing SE10.
- Map `status == 409 && reason == "phone_taken"` ahead of the `409` catch-all.
- In `thenAfter`, add `Refusal.PhoneTaken -> Then.Mark(mapOf(Field.Phone to R.string.phone_taken))`.
- Add the string next to `already_caregiver`.

- [ ] **Step 5: Run the Android checks**

Run (from `android/`): `./gradlew ktlintCheck :app:testDebugUnitTest`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 6: Commit**

```bash
git add android/app/src
git commit -m "feat(android): explain phone_taken on the senior form (SE10)"
```
