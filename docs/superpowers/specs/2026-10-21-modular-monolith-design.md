# Modular monolith by table ownership: design

**Date:** 2026-10-21
**Status:** Approved in conversation; awaiting review of this document
**Classification:** Architectural
**Scope:** `backend/app/`, `backend/tests/`, `backend/scripts/`, `backend/pyproject.toml` (import contracts), `backend/AGENTS.md`, `docs/adr/ADR-005-modular-monolith.md`, `docs/specs/echocare/01-architecture.md` §8
**Follows:** [ADR-005](../../adr/ADR-005-modular-monolith.md), which holds the evidence (the write map) and the options considered. This document is what to build. It changes ADR-005 on three points: identity (ADR group D) is done now by merging `staff` into `auth`; the package order becomes an explicit, exhaustive layers contract; and `agent` gets a strict rule of its own.

---

## 1. Goal and why

The scheduler and the agent loop are the next two parts to build (06 §2, 01 §8). Both write tables that other packages own: the scheduler queues, dials, redials and cancels calls, and the agent loop stores turns and answers and ends calls, after which the result runs into the senior's code and possibly an incident. Every table's owner, and the owner's write functions, should be in place first, so both parts are built against those functions from their first line instead of being cleaned up afterwards.

Success means:

- **Every table has one owner** (§4), and only the owner writes its rows. A test fails on any other write, with no exceptions.
- **The package order is written down** (§5). Every package under `app/` is placed in a layer, a package may import only from layers below its own, and a new package fails `lint-imports` until it is placed.
- **`agent` exists** and imports only `voice`, `core` and `status`. It is the package ADR-004 names as the first to leave the process, so what it imports from `voice` is the interface a later split would need.
- **`staff` is gone.** Its code lives in `auth`, which owns all of identity.
- **Nothing a client can see changes.** Same endpoints and JSON, same database, no migration, and every existing test passes (585 on 2026-10-21, apart from test files that move).

## 2. What is wrong today

The full evidence is in ADR-005's context: a write map built from a static scan and a traced test run. In short, 30 of the 44 (function, table) write pairs in `app/` write a table defined in another package. They fall into four groups:

| Group | Pairs | What happens | Fix (§6) |
|---|---|---|---|
| A | 4 | Tables filed in the wrong package: `campaigns` writes `Campaign`, which is defined in `voice/models.py`; `calls/ending.py` is the only writer of `SeniorStatus` (in `seniors`) and `StatusReport` (in `voice`) | Move the classes |
| B | 9 | `calls/ending.py` and `calls/mock.py` write a call's result straight into `seniors`, `consents`, `incidents`, `calls`, `call_turns`, `answers` | Owner functions |
| C | 5 | `calls/service.py` and `campaigns` queue and cancel `calls` rows by hand | Owner functions in `voice` |
| D | 12 | `staff` (7) and `seniors` (5) write `users` and `grants`, which `auth` defines | Merge `staff` into `auth`; `seniors` uses `auth` functions |

Symptoms already present: the enrollment move written twice (`seniors.service.move()` and `calls/ending.py:192`), `queued → canceled` written in three places outside `voice`, `caregivers_query` copied and already different, and the "may this name be changed" rule split between `staff.edit_staff()` and `seniors.edit_caregiver()`.

## 3. Target layout

```
app/
├── main.py             drops the staff router
├── models/__init__.py  imports from the new homes
├── core/               no change
├── status/             no change: pure rules and matrix
├── auth/      models · schemas* · service* · router*      + everything from staff/
├── codes/     models · service                            new: the senior's code and its reports
├── seniors/   models* · schemas · service* · router
├── voice/     models* · service* · router* · calls · dialogue* · twilio
├── agent/     session · relay                             new: from voice/session.py and Relay
├── incidents/ models · schemas · service* · router
├── campaigns/ models · schemas* · service* · router       models.py new
├── calls/     schemas · service* · ending* · mock* · router
└── system/             no change
                                       * changed
```

`staff/` is deleted. Tests follow their code:
- `tests/staff/` moves to `tests/auth/`.
- The `serve()` tests in `tests/voice/test_voice.py`, and the `Relay` test in `tests/voice/test_relay.py`, move to `tests/agent/`. `test_relay.py` also tests `voice.twilio` signatures and `voice.calls` callback rules; those tests stay in `tests/voice/`, so that file is split, not moved.
- `tests/architecture/test_contracts.py`'s "new package and an old one import each other" case imports `app.staff` and names the `acyclic_siblings` contract, so it is rewritten against `auth` and the new layers contract.

## 4. Table ownership

| Table | Owner | Moves |
|---|---|---|
| `users`, `grants`, `push_tokens` | `auth` | none |
| `seniors`, `consents`, `watch_states` | `seniors` | none |
| `senior_statuses`, `status_reports` | `codes` | `SeniorStatus` from `seniors/models.py`; `StatusReport` and its `ReportSource` enum from `voice/models.py` |
| `calls`, `call_turns`, `answers` | `voice` | none |
| `incidents`, `events` | `incidents` | none (`events` gets a writer when event intake is built) |
| `campaigns` | `campaigns` | `Campaign`, `CampaignKind`, `WarningLevel` from `voice/models.py` |

**The owner is the package whose `models.py` defines the class.** No separate list is kept, so moving a class is how ownership changes. Enums move with the table that stores them; enums used by several tables stay where they are.

The call tables stay in `voice`, not in `calls`, although `calls/` writes them most. `incidents` and `campaigns` read call rows, and `calls/` writes incidents and calls into `campaigns`, so the owner of the call rows has to sit below all three.

## 5. Package order and contracts

### 5.1 Order

```
calls | agent | system      flows: orchestrate across owners
campaigns
incidents
voice                       call rows, lifecycle, Twilio
seniors
auth | codes
core | status               basics: import nothing from app/
```

A package may import from any layer below its own (relaxed layering, the only kind import-linter's `layers` contract offers). `|` marks independent siblings, which may not import each other, directly or through a chain. Routers are composition roots and stay exempt, as today (`ignore_imports = ["app.**.router -> app.**"]`), so `voice/router.py` may import `agent` and `seniors/router.py` may import `calls`.

This order matches today's imports once the moves in §4 and §6 are made. It was checked against the cross-package import list of 2026-10-21. The build checks it again by running `lint-imports`.

### 5.2 Contracts in `pyproject.toml`

1. **One `layers` contract for the packages**, with the order above, `containers = ["app"]`, `exhaustive = true` and `exhaustive_ignores = ["main", "models"]`. It replaces `acyclic_siblings`, which it implies. *If import-linter refuses the root package as a container,* list the layers by full name instead, and add a test to `tests/architecture/test_contracts.py` that every package under `app/` appears in the contract. That keeps the "a new package must be placed" property.
2. **`agent` imports only `voice`, `core` and `status`.** A `forbidden` contract from `app.agent` to `app.*`, with `ignore_imports` for `app.agent.** -> app.voice.**`, `-> app.core.**`, `-> app.status.**` and `-> app.agent.**`, and `allow_indirect_imports = true` (`voice` itself imports `seniors`). The wildcard means a package added later is forbidden too. Set `unmatched_ignore_imports_alerting` so that an ignore line matching nothing yet (`agent` may not import `status` today) isn't an error. *If import-linter rejects `app.agent` being both the source and inside the forbidden `app.*`,* list the forbidden packages by name, and add a test to `test_contracts.py` that the list names every package under `app/` except `agent`, `voice`, `core` and `status`.
3. The other contracts stay as they are. The pure-`status` contract and its dependency check are untouched.

### 5.3 The ownership test

A new test in `tests/architecture/test_contracts.py`, next to `test_package_inits_import_nothing`. It reads the files and fails when a module in package X writes a table owned by package Y ≠ X. Here, writing means:

- constructing an ORM class (`Call(...)`): insert;
- `insert(C)`, `update(C)`, `delete(C)`;
- `row.column = …` and `setattr(row, …)` on a variable whose class is known from its annotation, its constructor, or `select(C)` / `session.get(C, …)`;
- `session.delete(row)`.

It covers `app/` only (scripts and tests may write anything). It has no exceptions once §6 is done. Its known limit: an assignment to a row whose class the scan can't work out is missed, and a reviewer has to catch it. Like the import contracts, it gets a planted-violation case: a copy of `app/` with one foreign write added must fail.

## 6. What changes, package by package

### 6.1 Owner write functions: the rule

A function that another package calls to write the owner's tables:

- takes the caller's `AsyncSession` and **does not commit**, so the caller keeps one transaction around its whole flow;
- **reports failure in its return value** (`None`, `False`, a result), never with `refuse()`, because only the caller knows which HTTP answer fits;
- is a real step of the owner's rules, not a setter. A function whose only job is forwarding a write to a lower package is a sign that something is in the wrong place.

The HTTP-shaped functions that commit and refuse (`seniors.service.move()`, `staff`'s `grant_staff()`, and so on) can stay for their own routers. How they share code with the new functions is up to the builder.

The three emergency-path rules must stay in one transaction, as today: a red code stays while its incident is unresolved (03 §8), at most one live call per senior (05 §3, the partial unique index the campaign's `INSERT … SELECT` relies on), and a campaign skips seniors with an unresolved incident.

### 6.2 `auth` absorbs `staff` (group D)

- `staff/service.py`, `schemas.py` and `router.py` move into the matching `auth` files. The `/staff…` paths are already full paths, so the API is unchanged. `main.py` mounts one router fewer.
- `user_for()` moves to `auth`. It makes the user row behind a grant of any role (01 §6), so `seniors` imports it from there.
- `seniors`' grant and user writes go through `auth` functions: the senior's own grant (`sync_senior_grant`), caregiver grant, caregiver edit (name and relation) and revoke. `auth` sits below `seniors` and may not import it, so these functions take plain values (ids, phone, names), not a `Senior`.
- The rename rule moves to one place in `auth`: a das or medic's name changes only through `PATCH /staff/{userId}`, and a caregiver edit that would rename one is refused (Q22).
- `scripts/grant_das.py` imports `grant_staff` from `auth`.

### 6.3 `codes` (group A)

- New `codes/models.py` with `SeniorStatus`, `StatusReport` and `ReportSource`, moved unchanged (same table names, columns, indexes).
- New `codes/service.py` with `set_code()` (moved from `calls/ending.py`) and a function that writes a status report.
- `codes` imports only `core` and `status`. Readers (`seniors`, `incidents`, `calls`) import its models for their joins.
- Deciding the code (`next_code`, the unresolved-incident check) stays in `calls/ending.py`, the flow. `codes` stores the decision and doesn't make it.

### 6.4 `campaigns` gets its model (group A)

New `campaigns/models.py` with `Campaign`, `CampaignKind` and `WarningLevel`, moved unchanged. `voice` stops defining them. Nothing in `voice` uses them; `Call.campaign_id` keeps its string foreign key.

### 6.5 `voice`: the call lifecycle (groups B and C)

`voice` offers the functions the call rows need from outside, shaped by what the scheduler and the agent loop will also call:

| Need | Today written by | Function (names are suggestions) |
|---|---|---|
| Queue calls: a campaign's `INSERT … SELECT`, a welcome call, a redial | `campaigns.start_campaign`, `calls.service.queue_welcome_call`, `calls.ending.conclude` | `queue_calls()` |
| Cancel queued calls: a lapsed campaign, an ended campaign, a withdrawn senior | `campaigns.cancel_lapsed`, `end_campaign`, `calls.service.cancel_queued_calls` | `cancel_queued()` |
| Picked up: to `in_progress`, `started_at` | `calls.mock.answer_mock_call`, `answer_welcome` | `answer()` |
| Ended: end state, `ended_at`, and result fields (`final_severity`, `final_certainty`, `reason`, `summary`, `welcome_outcome`) | `calls.ending.conclude`, `conclude_welcome`, `calls.mock` | `finish()` |
| Transcript | `calls.mock.turns`, `voice.session` (moving to `agent`) | `add_turns()` |
| Extracted answers | `calls.mock` | `record_answers()` |

Every state change goes through `advance()`, including bulk cancels. `move_call()` stays the Twilio callbacks' way in. The mock and the real call go through the same functions, so the mock tests what the real call runs.

`queue_calls()` keeps today's two behaviours on the one-live-call index. A welcome call and a campaign's calls are skipped on conflict (`on conflict do nothing`). A redial is inserted without that clause, so a conflict raises instead of silently dropping the redial. Don't merge them into one silent insert.

### 6.6 `seniors` and `incidents` (group B)

- `seniors.confirm_welcome()`: the welcome call's `accepted → active/refused` compare-and-set plus its consent row, without committing. `calls/ending.py:192`'s hand-written update is deleted.
- `incidents.open_incident()`: inserts the incident a red opens. `opens_incident()` (the rule) and the insert end up in the same package.
- `incidents` reads `seniors.caregivers_query()` and deletes its own copy. The incident view's caregiver list keeps its shape: `CaregiverSummary` ignores the extra `user_id`. The one difference is that two caregivers with the same name now come back in a fixed order (the `User.id` tie-break), where before their order was undefined.

### 6.7 `agent`

- `agent/session.py`: `serve()` and `Socket`, moved from `voice/session.py`. `agent/relay.py`: `Relay`, `heard()`, `GOODBYE` and `Store`, moved from `voice/dialogue.py`.
- What stays in `voice/dialogue.py` is the TwiML side, which the voice router uses: `LANGUAGE`, `SORRY`, `twiml()`, `sorry()`, `greeting()` and the consent texts. `agent` imports `greeting` from there.
- `serve()` stops reading `Senior` and writing `CallTurn` itself. It gets the call's Twilio id and form of address, and stores turns, through `voice` functions (`voice.service.form_of_address()` already exists). It still commits after each turn, as today, so a dropped call keeps its transcript.
- `move_call()` commits ([voice/service.py:44](../../../backend/app/voice/service.py)), so it can't be the owner function `agent` calls. Split it into a core that doesn't commit, which `agent` uses, and the committing version the Twilio router keeps.
- `voice/router.py` imports `serve` from `agent`.
- `agent` never calls `calls.ending`. When the model loop is built, `serve()` returns the call's outcome and the router hands it on. That's for later; today's relay is the S1 echo test and has no outcome to hand on.

## 7. Constraints

- `backend/AGENTS.md` rules hold. Import a name from the module that defines it; no re-exports and no imports inside functions; ORM in `models.py`, Pydantic in `schemas.py`; `lint-imports`, `ruff` and `pytest` pass; tests use `echocare_test` only.
- **No migration.** Moving a class between files changes no table. `alembic check` against a local database at `head` must report no changes.
- **No API change.** `/api/openapi.json` before and after must be identical.
- **Deploys are not a constraint.** The app is in development, so the work may land in as many commits as it takes.
- Python 3.14, as the code already uses (e.g. `except A, B:`).

## 8. Non-goals and anti-goals

**Not in this work:** the scheduler, the notifier, the model-driven agent loop, event intake; renaming `voice` or `calls`; strict "only the layer below" rules for any package but `agent`; one Postgres schema per package; an event bus or outbox; making clients or the dashboard change.

**It has failed, even if every test passes, if:**

- one of the three emergency-path rules (§6.1) is split across two transactions;
- packages gain wrapper functions whose only job is to forward a call to a package further down;
- interface or facade modules re-export names (against `AGENTS.md`);
- a read that is one SQL join today becomes several queries stitched together in Python.

## 9. Verification

From `backend/`, with Postgres up (`docker compose up -d db`):

1. `uv run pytest`: everything passes. The count is 585 plus the new architecture tests.
2. `uv run lint-imports`: every contract kept, including the new layers and `agent` contracts.
3. `uv run ruff check .` and `uv run ruff format --check .`.
4. `alembic check` reports no changes.
5. `/api/openapi.json`, saved before the first change and after the last, is byte-identical.
6. The ownership test and the planted-violation cases pass. Delete one owner function call and put the direct write back: the ownership test must fail.

## 10. Documents to update

- `docs/adr/ADR-005-modular-monolith.md`: group D done by the merge (no longer deferred), the layers contract, `agent`'s strict rule, and the status.
- `backend/AGENTS.md`: the layout (no `staff/`; `codes/`, `agent/` and `campaigns/models.py` added) and two rules: only a table's owner writes it, and every package sits in a layer.
- `docs/specs/echocare/01-architecture.md` §8: an "Owns" column in the module table.

## 11. Decisions made in conversation, and calls left to the builder

**Decided with the user:** do ADR-005 groups A–C; create `codes`; move the relay into `agent` in this branch; merge `staff` into `auth` (not the other way round) in this branch; relaxed layering with a declared, exhaustive order; strict imports for `agent` only; deploys don't constrain the work.

**My calls (the designer's), open to change:** `system` sits in the flows layer as an independent sibling; `agent`'s module names (`session`, `relay`); `staff`'s code goes into `auth`'s existing four files, not a separate module; the `codes` service function names; how §7's "no migration" and "no API change" are proven; splitting `move_call()` into a core that doesn't commit and a committing version; keeping the redial's raise-on-conflict apart from the silent skip; accepting the fixed order for same-name caregivers; and the fallback contracts in §5.2 if import-linter rejects the first form. The staff routes stay after `auth`'s own routes in the merged router, so `/api/openapi.json` keeps its path order.

**Left to the builder:** the signatures of every owner function in §6; the order of the steps, with one commit per step on the branch; how the ownership test infers a row's class; how HTTP-shaped functions reuse the new owner functions.
