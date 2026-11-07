# Modular monolith by table ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every table one owning package that alone writes it, fold `staff` into `auth`, add `codes` and `agent`, and enforce ownership, the package order and `agent`'s narrow imports in CI, with no change a client can see.

**Architecture:** A test that reads `app/` lists every write to a table owned by another package. It starts with an exact allow-list of today's 16 (module, table class) pairs, and each task deletes the pairs it fixes until the list is empty. Class moves (`codes`, `campaigns`) and new owner functions (`auth`, `voice`, `seniors`, `incidents`) remove the pairs. The last task replaces `acyclic_siblings` with an exhaustive layers contract and adds `agent`'s contract.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async with asyncpg, Postgres 18, Alembic 1.20, import-linter 2.15, pytest.

**Spec:** [docs/superpowers/specs/2026-10-21-modular-monolith-design.md](../specs/2026-10-21-modular-monolith-design.md), building on [ADR-005](../../adr/ADR-005-modular-monolith.md). Read both before Task 0. §4 is the ownership table, §5 the order and contracts, §6 the owner functions.

## Global Constraints

- Branch `modular-monolith`, which holds the design commit. Don't push and don't open PRs.
- Backend commands from `backend/`, with Postgres up (`docker compose up -d db` from the repository root). `SCRATCH` is `/private/tmp/claude-501/-Users-paulhondola-Developer-EchoCare/9b4439cf-50e4-41d9-a784-ff004788e99f/scratchpad`.
- `backend/AGENTS.md` applies: import a name from the module that defines it; no imports inside functions; `__init__.py` files stay empty; ORM in `models.py`, Pydantic in `schemas.py`. `uv run lint-imports` passes **without changing a contract** until Task 8, which changes exactly the contracts the spec names.
- **Moves keep their bodies.** A moved function, class or endpoint keeps its name, signature, docstring and code, unless this plan gives a new signature. Endpoint function names and docstrings feed `/api/openapi.json`.
- **Owner functions** (spec §6.1) take the caller's `AsyncSession`, never commit, never `refuse()`, and report failure in their return value.
- **No migration:** `tests/core/test_models.py::test_models_match_the_migration` (`alembic check`) keeps passing.
- **No API change:** at the end, `/api/openapi.json` is byte-identical to the dump from Task 0.
- Tests patch a name in the module that uses it. When a name moves, its `monkeypatch.setattr` targets move with it.
- Test module basenames are unique across `backend/tests/`, since pytest runs without `__init__.py`.
- Comments are English and cite the spec by ID (`05 §3`, `ADR-005`, `Q22`). Romanian strings are copied unchanged.
- Commit with the hooks on: never `--no-verify` or `LEFTHOOK=0`. End every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A campaign starts while a senior already has a live call.** That senior keeps the one call and gets no second; the others are queued. *Test in Task 4.*
2. **A redial collides with a live call.** It raises; it is not silently dropped (spec §6.5). *Test in Task 4.*
3. **Twilio skips a state** (`completed` with no `in-progress` before it). The call still ends `completed` with `started_at` set, because `move_call` keeps `after_callback` and doesn't go through `advance()`. *Test in Task 5.*
4. **The relay socket drops mid-call.** Every turn stored before the drop stays, because the agent commits after each turn. *Test in Task 7.*
5. **Two caregivers with the same name in an incident view** come back in `User.id` order (spec §6.6). *Test in Task 6.*

---

### Task 0: Baseline, and the ownership test with today's allow-list

**Files:**
- Modify: `backend/tests/architecture/test_contracts.py` (append)

**Interfaces:**
- Produces: `foreign_writes(app: Path) -> set[tuple[str, str]]` in `test_contracts.py`, returning `(module path relative to app/, ORM class name)` for every write by a module outside the class's package. Also `KNOWN: set[tuple[str, str]]`, which every later task edits.

- [ ] **Step 1: Save the API baseline**

Run: `uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=1, ensure_ascii=False))" > $SCRATCH/openapi-before.json && uv run pytest -q | tail -1`
Expected: the file is non-empty, and `585 passed`.

- [ ] **Step 2: Write the tests**

```python
# Today's foreign writes (ADR-005's write map); each task deletes the pairs it fixes.
KNOWN = {
    ("staff/service.py", "User"), ("staff/service.py", "Grant"),
    ("seniors/service.py", "User"), ("seniors/service.py", "Grant"),
    ("calls/ending.py", "SeniorStatus"), ("calls/ending.py", "StatusReport"),
    ("calls/ending.py", "Call"), ("calls/ending.py", "Incident"),
    ("calls/ending.py", "Senior"), ("calls/ending.py", "Consent"),
    ("calls/mock.py", "Call"), ("calls/mock.py", "Answer"), ("calls/mock.py", "CallTurn"),
    ("calls/service.py", "Call"),
    ("campaigns/service.py", "Campaign"), ("campaigns/service.py", "Call"),
}

def test_only_the_owner_writes_a_table():
    assert foreign_writes(BACKEND / "app") == KNOWN

LEAK = '''from app.seniors.models import Senior

def make():
    return Senior(full_name="x")

def rename(senior: Senior):
    senior.full_name = "y"
'''

def test_a_foreign_write_is_found(tmp_path):
    shutil.copytree(BACKEND / "app", tmp_path / "app", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "app/system/leak.py").write_text(LEAK)
    assert {("system/leak.py", "Senior")} <= foreign_writes(tmp_path / "app")
```

- [ ] **Step 3: Run them to see them fail**

Run: `uv run pytest tests/architecture/test_contracts.py -k "owner or foreign" -v`
Expected: FAIL with `NameError: name 'foreign_writes' is not defined`.

- [ ] **Step 4: Implement `foreign_writes(app: Path) -> set[tuple[str, str]]`**

*Offer this step to the user first; they asked to write its core rule.* The rules come from spec §5.3:
- Owners: each `class X(Base)` in `app/<pkg>/models.py` is owned by `<pkg>`. Skip `app/models/` and every `models.py` as writers.
- A write is any of: a call `X(...)`; `insert(X)`, `update(X)` or `delete(X)`; `v.attr = …` or `setattr(v, …)`; or `session.delete(v)`.
- The class of `v` comes from, in order:
  - its annotation in the enclosing function's parameters;
  - its assignment from `X(...)`, `select(X)…` or `session.get(X, …)`;
  - otherwise, when `attr` is a column of exactly one ORM class, that class.
- `self` is never a row.

- [ ] **Step 5: Run them to see them pass**

Run: `uv run pytest tests/architecture/test_contracts.py -v`
Expected: PASS. If the found set differs from `KNOWN`, compare with ADR-005's write map, which is the reference. Fix the scan; don't edit `KNOWN` to match a wrong scan.

- [ ] **Step 6: Commit**

```bash
git add tests/architecture/test_contracts.py
git commit -m "test(backend): list writes to another package's tables (ADR-005)"
```

---

### Task 1: `staff` folds into `auth`; `seniors` writes identity through `auth`

**Files:**
- Modify: `backend/app/auth/service.py`, `schemas.py`, `router.py`, `backend/app/main.py`, `backend/app/seniors/service.py`, `backend/scripts/grant_das.py`, `backend/scripts/seed.py`, `backend/AGENTS.md` (layout)
- Delete: `backend/app/staff/`
- Move: `backend/tests/staff/test_grants.py`, `test_staff.py` → `backend/tests/auth/`
- Test: `backend/tests/architecture/test_contracts.py` (`KNOWN`; the cycle case)

**Interfaces:**
- Produces, in `app/auth/service.py`:
  - moved unchanged: `user_for`, `grant_staff`, `staff_listings`, `edit_staff`, `revoke_staff`, `set_on_duty`, `STAFF_ROLES`, `STAFF_LOCK`. They log through `auth`'s `log`.
  - `sync_senior_grant(session: AsyncSession, senior_id: uuid.UUID, phone_e164: str, display_name: str, *, landline: bool, granted_by: uuid.UUID) -> bool`: today's body, reading plain values. `seed.py` passes `granted_by=senior.medic_id`; `seniors` passes `display_name=senior.full_name[:120]`.
  - `add_caregiver_grant(session: AsyncSession, senior_id: uuid.UUID, phone_e164: str, display_name: str, relation: str, granted_by: uuid.UUID) -> User | None`: `None` when the number already held that caregiver grant. The caller rolls back and refuses 409 `already_done`, as today.
  - `edit_caregiver_grant(session: AsyncSession, user: User, grant: Grant, *, display_name: str | None, relation: str | None) -> bool`: `False`, with nothing changed, when `display_name` is given and `user` holds a das or medic grant (Q22). The caller refuses 403 `not_allowed`, as today.
  - `revoke_caregiver_grant(session: AsyncSession, senior_id: uuid.UUID, user_id: uuid.UUID) -> None`.
- Produces: `auth/schemas.py` gains `staff/schemas.py`'s classes and aliases. `auth/router.py` gains the six `/staff` endpoints, after its own.

- [ ] **Step 1: Point the tests at `auth`**

`git mv tests/staff/*.py tests/auth/`. In them, `from app.staff.service import user_for` becomes `from app.auth.service import user_for`. In `KNOWN`, delete the four `staff/…` and `seniors/…` pairs. In `test_contracts.py`'s "new package and an old one import each other" case, `app.staff.service` becomes `app.auth.service` and `app/staff/clock.py` becomes `app/auth/clock.py`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/auth tests/architecture -q`
Expected: FAIL with `ImportError: cannot import name 'user_for' from 'app.auth.service'`, and `test_only_the_owner_writes_a_table` showing the four pairs.

- [ ] **Step 3: Move `staff` into `auth`, and add the four owner functions**

Move `staff/{service,schemas,router}.py` into the matching `auth` files. Delete `app/staff/` and its `include_router` in `main.py`. Point `seniors.service.register`, `edit`, `grant_caregiver`, `edit_caregiver` and `revoke_caregiver` at the new functions. Their HTTP behaviour (status codes, reasons, rollbacks, commits) stays in `seniors`. Update the imports in `scripts/grant_das.py` and `scripts/seed.py`. Remove `staff/` from the layout in `backend/AGENTS.md`, and add `staff roles, on duty` to `auth/`'s line.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q && uv run lint-imports`
Expected: 587 passed (585 + Task 0's two); contracts kept.

- [ ] **Step 5: Commit**

```bash
git add -A app/auth app/staff app/main.py app/seniors scripts tests AGENTS.md
git commit -m "refactor(backend): fold staff into auth; seniors writes grants through auth (ADR-005)"
```

---

### Task 2: `codes` owns the senior's code and its reports

**Files:**
- Create: `backend/app/codes/__init__.py` (empty), `backend/app/codes/models.py`, `backend/app/codes/service.py`
- Modify: `backend/app/seniors/models.py`, `backend/app/voice/models.py`, `backend/app/calls/ending.py`, `backend/app/models/__init__.py`, every importer of the three moved names (`seniors/service.py`, `incidents/service.py`, `calls/service.py`), `backend/AGENTS.md` (layout)
- Test: `backend/tests/architecture/test_imports.py`, `test_contracts.py` (`KNOWN`)

**Interfaces:**
- Produces, in `app/codes/models.py`: `SeniorStatus`, `StatusReport` and `ReportSource`, moved unchanged.
- Produces, in `app/codes/service.py`:
  - `set_code(session: AsyncSession, senior_id: uuid.UUID, call_id: uuid.UUID, code: Severity, reason: str, since: datetime) -> None`, with today's upsert.
  - `add_report(session: AsyncSession, call_id: uuid.UUID, source: ReportSource, severity: Severity, reason: str, *, certainty: Certainty | None = None) -> None`.
- `codes` imports only `app.core` and `app.status`.

- [ ] **Step 1: Write the failing tests**

Add `"app.codes.models"` to `test_imports_first`'s list. In `KNOWN`, delete `("calls/ending.py", "SeniorStatus")` and `("calls/ending.py", "StatusReport")`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/architecture -q`
Expected: FAIL: `No module named 'app.codes'`, and the ownership test shows the two pairs.

- [ ] **Step 3: Create `codes` and point `calls/ending.py` at it**

`ending.py` calls `set_code` and `add_report` in place of its own upsert and its `StatusReport(...)` constructors. Deciding the code (`next_code`, the unresolved check) stays in `ending.py`. Add `codes/  the senior's code and its status reports` to the AGENTS.md layout.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q && uv run lint-imports`
Expected: all pass, including `test_models_match_the_migration`.

- [ ] **Step 5: Commit**

```bash
git add -A app tests AGENTS.md
git commit -m "refactor(backend): codes owns senior_statuses and status_reports (ADR-005)"
```

---

### Task 3: `campaigns` owns its table

**Files:**
- Create: `backend/app/campaigns/models.py`
- Modify: `backend/app/voice/models.py`, `backend/app/campaigns/schemas.py`, `service.py`, `backend/app/calls/ending.py`, `mock.py`, `backend/app/models/__init__.py`, `backend/AGENTS.md`
- Test: `backend/tests/architecture/test_imports.py`, `test_contracts.py` (`KNOWN`)

**Interfaces:**
- Produces, in `app/campaigns/models.py`: `Campaign`, `CampaignKind` and `WarningLevel`, moved unchanged. `Call.campaign_id` keeps its string foreign key `"campaigns.id"`.

- [ ] **Step 1: Write the failing tests**

Add `"app.campaigns.models"` to `test_imports_first`. In `KNOWN`, delete `("campaigns/service.py", "Campaign")`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/architecture -q`
Expected: FAIL: `No module named 'app.campaigns.models'`.

- [ ] **Step 3: Move the classes and update their importers**

Add `models` to `campaigns/`'s line in the AGENTS.md layout.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q && uv run lint-imports`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A app tests AGENTS.md
git commit -m "refactor(backend): campaigns owns its table (ADR-005)"
```

---

### Task 4: `voice` queues and cancels calls

**Files:**
- Modify: `backend/app/voice/service.py`, `backend/app/campaigns/service.py`, `backend/app/calls/service.py`, `backend/app/calls/ending.py`
- Create test: `backend/tests/voice/test_lifecycle.py`
- Test: `test_contracts.py` (`KNOWN`)

**Interfaces:**
- Produces, in `app/voice/service.py`:
  - `queue_calls(session: AsyncSession, senior_ids: Select, *, trigger: CallTrigger, due_at: datetime, campaign_id: uuid.UUID | None = None) -> None`: `INSERT … SELECT` of attempt 1, `starting_severity` green, `queued`, `ON CONFLICT DO NOTHING`. The welcome call passes `select(Senior.id).where(Senior.id == senior_id)`.
  - `queue_redial(session: AsyncSession, call: Call, due_at: datetime) -> None`: adds attempt `call.attempt + 1` with `call`'s trigger, campaign and starting severity, and `previous_call_id=call.id`. It has **no** conflict clause.
  - `cancel_queued(session: AsyncSession, *where: ColumnElement[bool], now: datetime) -> None`: `UPDATE calls SET state = advance(queued, canceled), ended_at = now WHERE state = queued AND <where>`.
- Consumes: `redial_delay()` stays in `calls/ending.py`. `ending` passes `now + redial_delay()`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_queue_calls_skips_a_senior_with_a_live_call(db, add_senior):
    busy, free = await add_senior("+40700000101"), await add_senior("+40700000102")
    db.add(Call(senior_id=busy.id, trigger=CallTrigger.manual,
                starting_severity=Severity.green, due_at=NOW))
    await db.commit()
    await queue_calls(db, select(Senior.id).where(Senior.id.in_([busy.id, free.id])),
                      trigger=CallTrigger.campaign, due_at=NOW)
    await db.commit()
    rows = (await db.execute(select(Call.senior_id, Call.trigger))).all()
    assert sorted(rows) == sorted([(busy.id, CallTrigger.manual), (free.id, CallTrigger.campaign)])

async def test_a_redial_that_collides_raises(db, add_senior):
    senior = await add_senior("+40700000101")
    first = Call(senior_id=senior.id, trigger=CallTrigger.campaign,
                 starting_severity=Severity.green, due_at=NOW, state=CallState.unanswered)
    live = Call(senior_id=senior.id, trigger=CallTrigger.manual,
                starting_severity=Severity.green, due_at=NOW)
    db.add_all([first, live])
    await db.commit()
    await queue_redial(db, first, NOW)
    with pytest.raises(IntegrityError):
        await db.flush()

async def test_cancel_queued_leaves_other_states_alone(db, add_senior):
    a, b = await add_senior("+40700000101"), await add_senior("+40700000102")
    queued = Call(senior_id=a.id, trigger=CallTrigger.manual, starting_severity=Severity.green, due_at=NOW)
    talking = Call(senior_id=b.id, trigger=CallTrigger.manual, starting_severity=Severity.green,
                   due_at=NOW, state=CallState.in_progress)
    db.add_all([queued, talking])
    await db.commit()
    await cancel_queued(db, Call.senior_id.in_([a.id, b.id]), now=NOW)
    await db.commit()
    await db.refresh(queued)
    await db.refresh(talking)
    assert (queued.state, queued.ended_at) == (CallState.canceled, NOW)
    assert (talking.state, talking.ended_at) == (CallState.in_progress, None)
```

`NOW = datetime(2026, 10, 21, 9, tzinfo=UTC)`. In `KNOWN`, delete `("campaigns/service.py", "Call")` and `("calls/service.py", "Call")`.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/voice/test_lifecycle.py tests/architecture -q`
Expected: FAIL with `ImportError: cannot import name 'queue_calls'`.

- [ ] **Step 3: Implement the three functions and point the callers at them**

The callers are `campaigns.service`'s `start_campaign`, `cancel_lapsed` and `end_campaign`; `calls.service`'s `queue_welcome_call` and `cancel_queued_calls`; and the redial in `calls/ending.py`.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q && uv run lint-imports`
Expected: all pass. `tests/campaigns` and `tests/calls` are unchanged and green.

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "refactor(backend): voice queues, redials and cancels calls (ADR-005 group C)"
```

---

### Task 5: `voice` writes a call's progress, transcript and answers

**Files:**
- Modify: `backend/app/voice/service.py`, `backend/app/calls/ending.py`, `backend/app/calls/mock.py`
- Test: `backend/tests/voice/test_lifecycle.py` (append), `backend/tests/voice/test_voice.py` (append; this test passes before the change and guards the `stamp()` refactor), `test_contracts.py` (`KNOWN`)

**Interfaces:**
- Produces, in `app/voice/service.py`:
  - `stamp(call: Call, state: CallState, now: datetime) -> None`: `started_at = now` on the first state in `ANSWERED`, and `ended_at = now` on a state in `ENDED`. `move_call` uses it in place of its own two `if`s and keeps `after_callback`.
  - `advance_call(call: Call, new: CallState, now: datetime) -> None`: `advance()`, then `stamp()`, only when the state changed.
  - `finish(call: Call, state: CallState, now: datetime, *, final_severity: Severity | None = None, final_certainty: Certainty | None = None, reason: str | None = None, summary: str | None = None, welcome_outcome: WelcomeOutcome | None = None) -> None`: `advance_call()`, then sets each field that isn't `None`.
  - `add_turn(session: AsyncSession, call_id: uuid.UUID, position: int, speaker: Speaker, kind: TurnKind, content: str) -> None`.
  - `record_answer(session: AsyncSession, call_id: uuid.UUID, field: Question, value: str, *, clear: bool, quote: str, at: datetime) -> None`.
- `calls/mock.py` loses `turns()`. Its transcript is `add_turn` per line, numbered from 1.

- [ ] **Step 1: Write the failing tests**

```python
def test_advance_call_stamps_once():
    call = Call(state=CallState.queued)
    advance_call(call, CallState.ringing, T1)
    assert (call.started_at, call.ended_at) == (None, None)
    advance_call(call, CallState.in_progress, T1)
    advance_call(call, CallState.completed, T2)
    advance_call(call, CallState.completed, T3)  # a repeat changes nothing
    assert (call.started_at, call.ended_at) == (T1, T2)

def test_advance_call_refuses_a_skip():
    with pytest.raises(InvalidTransition):
        advance_call(Call(state=CallState.queued), CallState.completed, T1)

def test_finish_keeps_what_it_is_not_given():
    call = Call(state=CallState.unanswered, ended_at=T1)
    finish(call, CallState.unanswered, T2, final_severity=Severity.yellow, reason="x")
    assert (call.ended_at, call.final_severity, call.reason, call.final_certainty) == (
        T1, Severity.yellow, "x", None)
```

`T1`, `T2` and `T3` are three distinct aware datetimes. In `KNOWN`, delete the three `calls/mock.py` pairs and `("calls/ending.py", "Call")`. Append to `tests/voice/test_voice.py`, since `move_call` now stamps through `stamp()`:

```python
async def test_a_skipped_state_still_counts_answered(client, db, call):
    for status in ("ringing", "completed"):
        await callback(client, "status", call.id, {**FIXTURES["status_common"], "CallStatus": status})
    stored_call = await stored(db, call)
    assert stored_call.state == "completed" and stored_call.started_at is not None
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/voice/test_lifecycle.py tests/architecture -q`
Expected: FAIL with `ImportError: cannot import name 'advance_call'`.

- [ ] **Step 3: Implement the functions; rewrite the call writes in `ending.py` and `mock.py`**

Each `call.x = …` in those two files becomes `advance_call` or `finish`. `conclude`'s unanswered path calls `finish(call, call.state, now, …)` so `ended_at` stays. Answers keep their `now + i µs` order.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q && uv run lint-imports`
Expected: all pass. `tests/calls/test_ending.py` and `test_mock_calls.py` are unchanged and green.

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "refactor(backend): voice writes a call's progress, transcript and answers (ADR-005 group B)"
```

---

### Task 6: `seniors` confirms the welcome, `incidents` opens the incident

**Files:**
- Modify: `backend/app/seniors/service.py`, `backend/app/incidents/service.py`, `backend/app/calls/ending.py`
- Test: `backend/tests/incidents/test_incident_view.py` (append), `test_contracts.py` (`KNOWN` → empty)

**Interfaces:**
- Produces:
  - `seniors.service.confirm_welcome(session: AsyncSession, senior_id: uuid.UUID, call_id: uuid.UUID, *, given: bool, method: ConsentMethod, text_version: str) -> bool`: the `accepted → active/refused` compare-and-set and its `Consent` row. `False`, with nothing written, if the senior isn't `accepted`.
  - `incidents.service.open_incident(session: AsyncSession, senior_id: uuid.UUID, call_id: uuid.UUID, reason: str) -> None`.
- `incidents/service.py` deletes its `caregivers_query` and uses `seniors.service.caregivers_query`.

- [ ] **Step 1: Write the failing tests**

Replace `KNOWN` with `set()`, and its assertion with `assert foreign_writes(BACKEND / "app") == set()`. Then append:

```python
async def test_same_name_caregivers_come_in_id_order(...):
    # an incident whose senior has two caregivers named "Ana Pop"
    detail = (await client.get(f"/api/incidents/{incident.id}", headers=das)).json()
    phones = [c["phone_e164"] for c in detail["caregivers"]]
    assert phones == [first.phone_e164, second.phone_e164]  # by User.id
```

Use the module's existing incident fixtures. `first` is the caregiver whose `User.id` sorts lower.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/incidents/test_incident_view.py tests/architecture -q`
Expected: FAIL. The ownership test lists `calls/ending.py` → `Incident`, `Senior`, `Consent`; the order test may pass or fail by chance.

- [ ] **Step 3: Implement both functions and point `conclude` / `conclude_welcome` at them**

`conclude_welcome` returns `False` when `confirm_welcome` does, before touching the call.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q && uv run lint-imports`
Expected: all pass, and the ownership test finds no foreign write.

- [ ] **Step 5: Commit**

```bash
git add app tests
git commit -m "refactor(backend): no package writes another's tables (ADR-005)"
```

---

### Task 7: `agent` holds the relay

**Files:**
- Create: `backend/app/agent/__init__.py` (empty), `backend/app/agent/relay.py`, `backend/app/agent/session.py`
- Modify: `backend/app/voice/dialogue.py`, `backend/app/voice/service.py`, `backend/app/voice/router.py`, `backend/AGENTS.md`
- Delete: `backend/app/voice/session.py`
- Move: `backend/tests/voice/test_relay.py` → `backend/tests/voice/test_twilio.py`, minus its `Relay` test
- Create test: `backend/tests/agent/test_relay.py`, with `test_a_scripted_session`, `Transcript` and `text()`, moved
- Test: `backend/tests/voice/test_voice.py`

**Interfaces:**
- Produces:
  - `app/agent/relay.py`: `Relay`, `Store`, `heard` and `GOODBYE`, moved from `voice/dialogue.py`, which keeps `LANGUAGE`, `SORRY`, the consent texts, `greeting`, `twiml` and `sorry`.
  - `app/agent/session.py`: `Socket` and `serve`, moved.
  - In `app/voice/service.py`:
    - `transition(session: AsyncSession, call_id: uuid.UUID, sid: str | None, new: CallState | None) -> CallState | None`: `move_call`'s body without the commit. `move_call` becomes `transition` + commit.
    - `live_call(session: AsyncSession, call_id: uuid.UUID) -> Row | None`: `(twilio_call_id, form_of_address)` of a call in `LIVE`, the query `serve` runs today.
    - `next_turn_position(session: AsyncSession, call_id: uuid.UUID) -> int`.
- `serve` imports only `app.voice.*`, `app.core.*` and `app.agent.*`. It stores a turn with `add_turn` and commits it. At its end it calls `transition(…, CallState.completed)` and commits.

- [ ] **Step 1: Write the failing tests**

Make the moves above. `test_voice.py` imports `from app.agent import session as agent_session` and `from app.agent.relay import GOODBYE`. Its three `serve()` tests stay there, because they drive Twilio callbacks through the voice router first. Append to `test_voice.py`:

```python
async def test_a_dropped_relay_keeps_its_turns(client, db, call):
    await answered(client, call)
    ws = Socket(call.id, [SETUP, {"type": "prompt", "voicePrompt": "Bine", "last": True}])
    await agent_session.serve(ws, call.id)  # the script runs out: WebSocketDisconnect
    turns = (await db.scalars(select(CallTurn.content).where(CallTurn.call_id == call.id))).all()
    assert "Bine" in turns
```

If `Socket` doesn't raise `WebSocketDisconnect` when its script runs out, make the second test's script end the way the existing tests do.

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/agent tests/voice -q`
Expected: FAIL with `No module named 'app.agent'`.

- [ ] **Step 3: Create `agent` and the three `voice` functions; repoint `voice/router.py`**

Add `agent/  the call session: relay socket and dialogue` to the AGENTS.md layout, and drop `dialogue relay` from `voice/`'s line.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q && uv run lint-imports && grep -rE "from app\.(seniors|incidents|codes|campaigns|calls|auth|system)" app/agent`
Expected: tests and contracts pass, and the grep prints nothing.

- [ ] **Step 5: Commit**

```bash
git add -A app tests AGENTS.md
git commit -m "refactor(backend): agent holds the relay and talks only to voice (ADR-005)"
```

---

### Task 8: The layer order and `agent`'s rule in CI; documents

**Files:**
- Modify: `backend/pyproject.toml`, `backend/tests/architecture/test_contracts.py`, `backend/AGENTS.md`, `docs/adr/ADR-005-modular-monolith.md`, `docs/specs/echocare/01-architecture.md`

**Interfaces:**
- Produces contract names that tests match on: `"Packages sit in layers; a new package must be placed (ADR-005)"` and `"The agent talks only to voice (ADR-004, ADR-005)"`.

- [ ] **Step 1: Write the failing cases**

In `CASES`, replace "new package and an old one import each other" with these three:

```python
"an old package imports a higher one": (
    {"app/auth/clock.py": "from app.seniors.service import reach\n"},
    "Packages sit in layers",
),
"a new package is not placed in a layer": (
    {"app/scheduler/__init__.py": "", "app/scheduler/service.py": "def tick(): ...\n"},
    "Packages sit in layers",
),
"agent imports seniors": (
    {"app/agent/leak.py": "from app.seniors.models import Senior\n"},
    "The agent talks only to voice",
),
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/architecture/test_contracts.py -q`
Expected: the three new cases FAIL (no contract by those names).

- [ ] **Step 3: Replace `acyclic_siblings` with the two contracts**

```toml
[[tool.importlinter.contracts]]
name = "Packages sit in layers; a new package must be placed (ADR-005)"
type = "layers"
containers = ["app"]
layers = [
    "calls | agent | system",
    "campaigns",
    "incidents",
    "voice",
    "seniors",
    "auth | codes",
    "core | status",
]
exhaustive = true
exhaustive_ignores = ["main", "models"]
ignore_imports = ["app.**.router -> app.**"]

[[tool.importlinter.contracts]]
name = "The agent talks only to voice (ADR-004, ADR-005)"
type = "forbidden"
source_modules = ["app.agent"]
forbidden_modules = ["app.*"]
ignore_imports = [
    "app.agent.** -> app.agent.**",
    "app.agent.** -> app.voice.**",
    "app.agent.** -> app.core.**",
    "app.agent.** -> app.status.**",
]
allow_indirect_imports = true
unmatched_ignore_imports_alerting = "none"
```

If import-linter rejects either form, use the fallback in spec §5.2: names in place of the container or wildcard, plus a completeness test in `test_contracts.py`.

- [ ] **Step 4: Run every check, and compare the API**

Run: `uv run pytest -q && uv run lint-imports && uv run ruff check . && uv run ruff format --check . && uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=1, ensure_ascii=False))" | diff - $SCRATCH/openapi-before.json && echo SAME`
Expected: everything passes, every contract is kept, and the last line is `SAME`.

- [ ] **Step 5: Update the documents (spec §10)**

- **ADR-005:**
  - Status becomes `Accepted`.
  - Group D is done by the merge; drop its "To revisit" bullet.
  - Add the layers contract and `agent`'s rule to the Decision.
  - Tick the action items done.
- **`backend/AGENTS.md`, under Rules:** add "Only a table's owner writes it: the package whose `models.py` defines it (ADR-005); others call the owner's functions. `test_only_the_owner_writes_a_table` enforces it." and "Every package sits in a layer of the layers contract; a new one must be placed there."
- **01 §8:** add an "Owns" column to the module table, using the tables from spec §4.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests AGENTS.md ../docs
git commit -m "build(backend): layers contract and agent's import rule; docs (ADR-005)"
```
