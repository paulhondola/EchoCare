# ADR-005: The backend becomes a modular monolith by table ownership, not by separate schemas

**Status:** Accepted, 2026-10-21; built on branch `modular-monolith` ([design](../superpowers/specs/2026-10-21-modular-monolith-design.md))
**Date:** 2026-10-21
**Deciders:** the team of four (backend owner first: every change lands on `api`)
**Builds on:** 01 §8 and §10, [ADR-004](ADR-004-api-runtime-and-add-ons.md) ("to revisit"), [backend layers design](../superpowers/specs/2026-10-16-backend-layers-and-schemas-design.md) §6

## Context

The question: microservices are ruled out (01 §1, §10; ADR-004). Several parts of the system stand mostly on their own: the agent loop, calls, the senior's status, incidents and campaigns. Can the backend become a modular monolith, one process with modules that have real boundaries, and is it worth building?

**It is most of the way there already.** 01 §8 already describes one process with modules "separate so that the dialer, the notifier and the call sessions can later become separate workers without a rewrite". The code has ten feature packages under `app/` (5,300 lines) and six import-linter contracts, all kept on 2026-10-21:

| Already enforced | How |
|---|---|
| One package per feature, `router → service → schemas → models` inside it | `layers` contract |
| No import cycles between packages | `acyclic_siblings`; routers are exempt (45 imports) because they compose packages |
| Only `app.main` mounts routers | `protected` contract |
| The rules and status engine is pure | `forbidden` contract, checked against every dependency in `pyproject.toml` |

**What is missing is ownership.** The contracts control *who imports whom*, not *who writes which table*. Any package may import another's `models.py` and write its rows.

**The write map, 2026-10-21.** It comes from two sources that agree. The first is a static AST scan of `app/`: constructors, `insert`/`update`/`delete` statements, `row.column = …`, `setattr` and `session.delete`. The second is a traced run of the 585 tests, which records each ORM `init`, each attribute `set` on a persistent row and each DML statement, and attributes it to the innermost `app/` frame. Every write site the scan found ran at least once under test, and the trace found no writer the scan missed.

Letters: **I** insert, **I\*** insert with `on conflict do nothing`, **S** upsert (`on conflict do update`), **U** update, **D** delete. A **bold** cell is a write from outside the package that defines the table.

| Table (defined in) | `auth` | `staff` | `seniors` | `voice` | `calls` | `campaigns` | `incidents` |
|---|---|---|---|---|---|---|---|
| `users` (auth) | U | **I\* U** | **U** | | | | |
| `grants` (auth) | | **I\* D** | **I\* U D**, cascade | | | | |
| `push_tokens` (auth) | S D | | | | | | |
| `seniors` (seniors) | | | I U D | | **U** | | |
| `consents` (seniors) | | | I D | | **I** | | |
| `watch_states` (seniors) | | | | | | | |
| `senior_statuses` (seniors) | | | | | **S** | | |
| `events` (incidents) | | | | | | | |
| `incidents` (incidents) | | | | | **I** | | U |
| `campaigns` (voice) | | | | | | **I U** | |
| `calls` (voice) | | | | U | **I I\* U** | **I\* U** | |
| `call_turns` (voice) | | | | I | **I** | | |
| `answers` (voice) | | | | | **I** | | |
| `status_reports` (voice) | | | | | **I** | | |

"Cascade": `grants.senior_id` has `ON DELETE CASCADE`, so `seniors.delete_draft()` also deletes the draft's grants. `grants.user_id` and `push_tokens.user_id` cascade from `users` too, but nothing in `app/` deletes a user. `watch_states` and `events` have no writer yet: event intake is not built, and only test fixtures fill them.

By function, 30 of the 44 (function, table) write pairs cross the package that defines the table. They fall into four groups, and each group has its own fix:

| Group | Pairs | Who writes | Fix |
|---|---|---|---|
| A. Table filed in the wrong package | 4 | `campaigns` → `campaigns` (start, end); `calls/ending.py` → `senior_statuses` (`set_code`), `status_reports` (`conclude`) | Move the class: `Campaign` to `campaigns/`; `SeniorStatus`, `StatusReport` and `set_code()` to `codes/` |
| B. A call's result, written by the orchestrator | 9 | `calls/ending.py` and `calls/mock.py` → `seniors`, `consents`, `incidents`, `calls`, `call_turns`, `answers` | Owner functions: `seniors.confirm_welcome()`, `incidents.open_incident()`, and the call-lifecycle functions in `voice` |
| C. Queueing and canceling calls | 5 | `calls/service.py` (welcome call, cancel on withdrawal), `campaigns` (start, lapse, end) → `calls` | `voice.queue_calls()`, `voice.cancel_queued()` |
| D. Identity | 12 | `staff` (7) and `seniors` (5) → `users`, `grants` | Deferred: see "To revisit" |

The calls tables stay in `voice`, not `calls`, even though `calls/` writes them most. `incidents` and `campaigns` read call rows, and `calls/` opens incidents and calls into `campaigns` (`mock.py` → `cancel_lapsed()`). So the owner of the call rows has to sit below all three, and the orchestrator above them. The `ending.py` docstring records the same constraint ("`voice` can't import `calls` (a cycle)").

This is already causing problems:

1. **The enrollment move is written twice.** `seniors.service.move()` moves a senior from one state to another with a compare-and-set. [`calls/ending.py:192`](../../backend/app/calls/ending.py) repeats the same `accepted → active/refused` move by hand, because `move()` commits and raises a 409 and so can't run inside another module's transaction.
2. **`queued → canceled` is written three times outside `voice`**: `calls/service.py:108`, `campaigns/service.py:180` and `:206`. The call lifecycle has an owner, `voice.service.move_call()` (row lock, `advance()`), and the bulk cancels skip it. It is correct today only because `queued → canceled` is an allowed transition.
3. **`caregivers_query` exists twice** (`incidents/service.py:97`, `seniors/service.py:199`), and the copies have drifted: the incidents copy has no `user_id` and no `User.id` tie-break.
4. **An incident's lifecycle is split.** It is opened in `calls/ending.py` and taken or resolved in `incidents/service.py`. The rule that decides whether to open one, `opens_incident()`, lives in `incidents`, but the insert does not.
5. **Tables live in the wrong package.** `Campaign`, `CampaignKind` and `WarningLevel` are in `voice/models.py`, though only `campaigns/` and `calls/` use them. `SeniorStatus` is in `seniors/models.py` and `StatusReport` in `voice/models.py`, yet both are written only by `calls/ending.py`.

**The package graph is a stack, not a set of modules.** Without router imports, the packages form a straight line:

```
calls → campaigns → incidents → voice → seniors → staff → auth → core
  (each one also imports everything below it, and the pure `status`)
```

Every package sits on all of the ones below, so the graph is acyclic only because it is fully ordered. A lower package can never call an upper one, so any flow that crosses modules ends up at the top (`calls/ending.py`) or in a router (`seniors/router.py` passes `then=queue_welcome_call` down to `accept()`). The scheduler, the notifier and the agent loop are all flows of this kind.

**The independent parts are mostly not built yet.** There is no scheduler loop (no lifespan task, 06 §2), no notifier (no Firebase messaging), no event intake (`Event` is defined but never written), and the agent loop is still the S1 echo relay (`voice/dialogue.py`). Drawing their boundaries now costs only a folder name.

**What the boundaries must not break.** Three emergency-path rules are cross-module and atomic today:

- A red code stays while its incident is unresolved (03 §8, P9). `conclude()` reads `incidents`, writes `senior_statuses` and opens the incident in one transaction.
- No senior ever has two live calls (05 §3). The partial unique index on `calls` does this, and the campaign's single `INSERT … SELECT` relies on it.
- A campaign skips seniors with an unresolved incident. That is a `NOT EXISTS` on `incidents` inside the same statement.

## Decision

1. **Every table has one owning package: the package whose `models.py` defines it.** Only the owner inserts, updates or deletes its rows. `test_only_the_owner_writes_a_table` in `tests/architecture/test_contracts.py` (an AST scan, like `test_package_inits_import_nothing`) fails on a foreign write. The owner is defined by where the class is declared, so moving a class is how ownership changes, and no separate list needs maintaining.
2. **Reads may cross freely.** Any package may `select` and `join` any other package's ORM classes. The incident detail, the dashboard lists and campaign progress are read models that span modules, and a join is the cheapest correct way to build them.
3. **Owners offer transaction-neutral write functions.** A function another module calls takes the caller's `AsyncSession`, does not commit, and reports failure in its return value, not with `refuse()`. `calls/ending.py` already works this way ("Nothing here commits: the caller owns the transaction"). The three atomic rules above stay in one transaction.
4. **Flows that cross modules live in the package or router that starts them**, as they do today: `calls/ending.py` for a call's result, routers for HTTP flows, and later `scheduler/` for timers. There is no event bus.
5. **Every package sits in a layer.** An exhaustive `layers` contract fixes the order below, and replaces `acyclic_siblings`. A package may import only from layers below its own, `|` siblings not from each other, and a new package fails `lint-imports` until it is placed. The layering is relaxed on purpose: a strict "only the layer directly below" rule would turn the incident view's single join into several queries, and would need pass-through functions for `ending.py`'s writes. Routers stay exempt; they compose the packages.

   ```
   calls | agent | system
   campaigns
   incidents
   voice
   seniors
   auth | codes
   core | status
   ```

6. **`agent` imports only `voice` and `status`.** A `forbidden` contract holds the one strict rule, for the package ADR-004 names as the first to leave the process. What it imports from `voice` is that split's interface: `open_line()`, `save_turn()` and `end_completed()`. These are the one exception to point 3: each opens and commits its own session, so the agent holds no database session, and a process boundary could replace them without touching it. It never calls `calls.ending`: the router hands the call's outcome on.
7. **Target map.** Only the rows marked *move* or *new* change.

| Package | Owns | Change |
|---|---|---|
| `auth` | `users`, `grants`, `push_tokens` | *move* everything from `staff/`, which owned no table and is gone; `seniors` writes its caregiver and senior grants through `auth` functions, and the Q22 rename rule lives here once |
| `seniors` | `seniors`, `consents`, `watch_states` | add `confirm_welcome()` (compare-and-set, no commit); `ending` uses it |
| `codes` *new, decided 2026-10-21* ("senior status") | `senior_statuses`, `status_reports` | *move* `SeniorStatus` from `seniors`, `StatusReport` from `voice`, and `set_code()` from `ending`; add a function that writes a status report. Imports only `core` and `status`, so `seniors`, `calls` and `incidents`, which read it, sit above it |
| `status` | nothing; pure rules and matrix | unchanged, contract unchanged |
| `voice` (dialer, call lifecycle, Twilio) | `calls`, `call_turns`, `answers` | add the call-lifecycle functions groups B and C need: `queue_calls()` (campaign, welcome), `queue_redial()` (raises on a conflict), `cancel_queued()` (its condition required), `advance_call()` and `finish()` (state, timestamps, result fields), `add_turn()`, `record_answer()`. `move_call()` stays the Twilio callbacks' way in, as `transition()` plus a commit, and the mock and the real call go through the same functions |
| `agent` *new* (call session, agent loop) | nothing; writes turns and answers through `voice` | *move* `voice/session.py` and `Relay`; reads and writes the call through `voice.open_line()`, `save_turn()` and `end_completed()`, which own their sessions (point 6); the model loop is built here |
| `incidents` | `incidents`, `events` until intake exists | add `open_incident()`; `ending` uses it |
| `campaigns` | `campaigns` | *move* `Campaign`, `CampaignKind`, `WarningLevel` from `voice/models.py` |
| `calls` | nothing; history, the mock, `ending` orchestration | `ending` hands its writes to the owners |
| `scheduler`, `notifier` *new* (06 §2, 01 §7) | nothing | built as packages under these rules |

`agent` is the boundary that matters most. ADR-004 names call sessions as the first part to move into a service of its own. If the agent loop only ever calls a short list of `voice` functions (store a turn, record an answer, report an alarm, end the call), that list is the interface a later split would need.

## Options considered

### A. Keep the current structure

| Dimension | Assessment |
|---|---|
| Complexity | None added |
| Cost | Zero now; grows with every flow that crosses modules |
| Scalability | Unchanged |
| Team familiarity | High |

**Pros:** nothing to do; the import contracts already stop cycles and keep the engine pure.

**Cons:** the five problems above stay, and the next three features (scheduler, notifier, agent loop) each write into `calls`, `senior_statuses` and `incidents`, so the write spread roughly doubles. The agent loop would grow on direct ORM access, and ADR-004's "move call sessions out along the module lines" would then mean a rewrite.

### B. Ownership of writes, shared reads, one transaction (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: class moves, five small owner functions, one test |
| Cost | About two days of mechanical work in four PRs (estimate); no migration (no table changes, only which file a class lives in; confirm with `alembic revision --autogenerate` producing an empty diff) |
| Scalability | Unchanged for load (ADR-004); keeps the agent split cheap |
| Team familiarity | High: the same packages, the same contracts, one more rule |

**Pros:** each state machine (enrollment, call lifecycle, incident, code) is written in one place; the three atomic rules stay atomic; new packages start with boundaries; reads stay simple.

**Cons:** reads still couple modules to each other's columns, so renaming a column means updating its readers (the "only add" rule, ADR-001 §2.3, already limits this). The AST test sees constructors and bulk writes, not `row.field = …` on a loaded row, so a reviewer still has to catch those.

### C. Strict modules: a Postgres schema per module, no cross-module joins or foreign keys, in-process events or an outbox

| Dimension | Assessment |
|---|---|
| Complexity | High: every read across modules becomes a composition of calls, and every rule across modules becomes an event |
| Cost | Weeks; rewrites `incidents/service.py`, `calls/service.py` and campaign progress, plus an outbox table and a dispatcher |
| Scalability | Lets any module become a service later; nothing in 06 §3 needs that |
| Team familiarity | Low |

**Pros:** clean extraction of any module later; modules can't see each other's tables at all.

**Cons:**
- **It breaks the atomic rules.** A red that must stay while its incident is unresolved, the one-live-call index used by the campaign's `INSERT … SELECT`, and the campaign skipping seniors with an unresolved incident would all become eventually consistent, on the emergency path. The SOS target is under 5 seconds (06 §5).
- **It is microservices without the network.** It brings in the costs ruled out in 01 §10 (a broker, in effect) while gaining none of the deployment independence.
- **The dashboard is a set of cross-module reads.** The incident detail alone joins `incidents`, `seniors`, `calls`, `call_turns`, `status_reports` and `grants`.

## Trade-off analysis

What matters is *where a row's rules live*, not *who can see the row*. Problems 1–5 all come from rules being written in more than one place. Every one of them is a write. None is a read. B fixes exactly that, keeping the transaction that holds the emergency-path rules together. C would also fix it, but it pays for that by breaking those same rules and rewriting the read side, which works today. A costs nothing until the scheduler and the agent loop arrive, and then it costs the most, because they are the two parts most likely to move out of the process later.

## Consequences

- **Easier:** finding the one place that changes a call's state, a senior's enrollment, an incident or a code; building the scheduler, notifier and agent loop as separate packages; moving the agent loop out of the process later (ADR-004) along an interface that already exists.
- **Harder:** a writer in another module has to call the owner instead of writing a row directly. Owners gain small functions that exist only for one caller. That is the price of keeping each rule in one place.
- **Unchanged:** one process, one replica, one database, one transaction per request; the HTTP contract (04); no migration.
- **To revisit:**
  - *Events from the notifier.* It is called after commit by whoever committed. A lost push is covered by the backstop re-read (01 §7), so it needs no outbox. Revisit only if a push must never be lost.
  - *Names.* `voice` owns the `calls` table while `calls/` owns none. Rename only if it confuses someone; renames touch every test that patches a name.
  - *Strict modules (C)*, only if a module really must leave the process, and then only for that module.

## Action items

Done on branch `modular-monolith`, one commit per step ([plan](../superpowers/plans/2026-10-21-modular-monolith.md)). Each step was checked with `lint-imports`, `pytest` (which runs `alembic check`), and, at the end, a byte-for-byte comparison of `/api/openapi.json`.

1. [x] The foreign-write test, starting from the 16 (module, table) pairs of the write map; each step below removed its pairs.
2. [x] Group D: `staff` folded into `auth`; `seniors` writes grants through `auth`.
3. [x] Group A: `codes/` owns `senior_statuses` and `status_reports`; `campaigns/models.py` owns `campaigns`.
4. [x] Group C: `voice.queue_calls()`, `queue_redial()` and `cancel_queued()`.
5. [x] Group B: the call-lifecycle functions in `voice`, `seniors.confirm_welcome()`, `incidents.open_incident()`; one `caregivers_query()`.
6. [x] `agent/` holds the relay and talks only to `voice`.
7. [x] The layers and `agent` contracts; the "Owns" column in 01 §8; `backend/AGENTS.md`.
8. [ ] Build `scheduler/` and `notifier/` under these rules (06 §2, 01 §7), each placed in a layer.
