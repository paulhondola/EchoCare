# Backend layers and schemas: design

**Date:** 2026-10-16
**Status:** Approved in conversation; awaiting review of this document
**Classification:** Architectural
**Scope:** `backend/app/`, `backend/tests/`, `backend/scripts/`, backend CI and hooks, `backend/AGENTS.md`
**Follows:** [2026-10-13 domain-driven restructuring](2026-10-13-domain-driven-architecture-restructuring-design.md). That spec split the flat backend into domain packages. This one fixes the seams between them. It supersedes that spec's §3.1 on two points: Pydantic schemas move out of `router.py`, and package `__init__.py` files are empty.

---

## 1. Goal

Clean up the seams between the domain packages so each one has the same parts in the same places, and keep them that way automatically.

Success means:

- Every feature package uses the same file roles: `models.py` (ORM), `schemas.py` (Pydantic), `service.py`, `router.py`.
- ORM and Pydantic classes can be told apart by file and by name.
- There is one import rule, and no imports inside functions.
- No import cycles, with the rules checked by `lint-imports` in CI and the pre-commit hook.
- No behavior change: endpoint paths, JSON shapes, database and migrations stay the same, and every existing test passes.

Not goals: new `01 §8` modules (scheduler, notifier, intake, call session), a generic CRUD base class, a repository layer, or moving `tests/` into subfolders.

## 2. What is wrong today

| # | Problem | Evidence |
|---|---|---|
| 1 | Three import styles for one symbol: submodule (`app.auth.service`), package facade (`app.auth`), global aggregator (`app.models`) | spread over `app/`, `scripts/`, `tests/` |
| 2 | Package `__init__.py` files re-export everything, routers included, so a light import loads the web layer | `voice/__init__.py` exports `Db`, `Params`, `answer`, `router`, … |
| 3 | A real import cycle, hidden by imports inside functions | moving `from app.models import Senior` to the top of `voice/router.py` breaks `import app.models`: `app.models → app.voice.models → app/voice/__init__.py → app.voice.router → app.models` (half-loaded) |
| 4 | Pydantic schemas in four kinds of file; `system/models.py` holds Pydantic, while every other `models.py` is ORM | `auth/router.py`, `staff/router.py`, `seniors/service.py`, `incidents/router.py`, `incidents/views.py`, `system/models.py` |
| 5 | Pydantic names that read like tables: `Turn` (table `CallTurn`), `Report` (`StatusReport`), `TriggerEvent` (`Event`), `Caregiver` (no table) | `incidents/views.py`, `seniors/service.py` |
| 6 | `/api/health` in `main.py` while `system/` exists; `main.py` re-exports `incidents_query` and `parse_statuses`, which nothing imports from there; the layout in `backend/AGENTS.md` lists neither `system/` nor `core/storage.py` | `app/main.py`, `backend/AGENTS.md` |

Leave the routers out and the packages already form a one-way graph:

```
incidents ─→ seniors ─→ staff ─→ auth ─→ core
    │           └────→ status ←──┐
    └────→ voice ────────────────┘
```

The only edges against that direction start in a router: `auth.router → seniors` (for `/me`) and `voice.router → app.models`. Routers are therefore the top layer, even though each one sits in a feature folder.

## 3. Target layout

```
app/
├── main.py              assembly only: logging, CORS, the /api router, include_router calls
├── core/                no change: db, settings, phones, storage
├── models/__init__.py   no change: the one ORM aggregator, for code outside app/
├── auth/        models · schemas* · service · router
├── staff/                schemas* · service · router
├── seniors/     models · schemas* · service · router
├── incidents/   models · schemas* · service · router        views.py removed
├── voice/       models ·            service* · router  + calls · dialogue · session · twilio
├── system/               schemas† · service · router       + /api/health
└── status/      alarms · engine     pure logic
                                     * new   † renamed from models.py
```

### 3.1 File roles

| File | Holds | May import from its own package |
|---|---|---|
| `__init__.py` | nothing | nothing |
| `models.py` | SQLAlchemy ORM tables, plus the enums their columns store | nothing above it |
| `schemas.py` | Pydantic request bodies and responses, and their field types and validators | `models`: enums only, never ORM classes. Kept by review; the layers contract allows any import downward |
| `service.py` | rules and queries; takes an `AsyncSession`; no endpoints | `schemas`, `models` |
| `router.py` | the controller: endpoints and request plumbing (dependencies, query-parameter parsing). Parse, call the service, return a schema | anything in its package |
| other logic files (`voice/calls.py`, `voice/dialogue.py`, `voice/session.py`, `voice/twilio.py`, `status/engine.py`, `status/alarms.py`) | one job each, named after it; at the same level as `service.py` | as needed, never `router` |

A package includes only the files it needs. Converting between ORM and Pydantic objects (`SeniorView.model_validate(senior, from_attributes=True)`) happens in `service.py` or `router.py`.

### 3.2 Move map

| What | From | To |
|---|---|---|
| `GrantView`, `Me` | `auth/router.py` | `auth/schemas.py` |
| `StaffGrant`, `StaffMember`, `StaffListing` | `staff/router.py` | `staff/schemas.py` |
| `SeniorDetail`, `Caregiver`, `SeniorForm`, `CaregiverForm`, `SeniorSummary`, `CaregiverView`, `MedicView`, `SeniorView`, and the field helpers `no_nul`, `text`, `State`, `OPTIONAL` | `seniors/service.py` | `seniors/schemas.py` |
| `REQUIRED_TO_SUBMIT` | `seniors/service.py` | stays, used by `missing_to_submit` |
| `IncidentSummary`, `Resolution`, `Note` | `incidents/router.py` | `incidents/schemas.py` |
| `TriggerEvent`, `Turn`, `Report`, `CallDetail`, `IncidentDetail` | `incidents/views.py` | `incidents/schemas.py` |
| `incident_query`, `calls_query`, `caregivers_query`, `attempts_behind`, `load_incident`, `call_detail` | `incidents/views.py` | `incidents/service.py` |
| `incidents_query`, `incident_summary`, `current_incident` | `incidents/router.py` | `incidents/service.py` |
| `parse_statuses` | `incidents/router.py` | stays (parses a query parameter) |
| `move_call` | `voice/router.py` | `voice/service.py` (new) |
| `twilio_params`, `Params`, `Db` | `voice/router.py` | stay (request plumbing) |
| `DatabaseHealth`, `SystemHealth` | `system/models.py` | `system/schemas.py` (file renamed) |
| `GET /health` | `main.py` | `system/router.py`. The router is mounted without a prefix, so the path stays `/api/health`, with no auth and still `SELECT 1` (06 §1) |
| re-export of `incidents_query`, `parse_statuses` | `main.py` | deleted |

`incidents/views.py` is deleted once it is empty.

## 4. Import rule

1. **Import a name from the module that defines it.** `from app.auth.service import refuse`, never `from app.auth import refuse`.
2. **Package `__init__.py` files are empty.** `auth`, `incidents`, `seniors`, `staff`, `status`, `system` and `voice` lose about 330 lines of re-exports. `core` already holds only a docstring, which may stay.
3. **`app/models/__init__.py` stays as the one aggregator, for code outside `app/` only:** `alembic/env.py` (autogenerate sees only the tables it imports; without them it would write a migration that drops them), `scripts/`, `tests/`. Inside `app/`, nothing imports it. The two uses in `voice/router.py` switch to `app.seniors.models`.
4. **No imports inside functions.** All four go to the top of their file.
5. **Tests patch a name in the module that uses it** (the `unittest.mock` "where to patch" rule). Each patched function has one call site:

   | Seam | Today | After |
   |---|---|---|
   | `hang_up` | `from app import voice` inside `amd()`; `tests/test_voice.py` patches `app.voice.hang_up` | `from app.voice.twilio import hang_up` at the top of `voice/router.py`; the test patches `app.voice.router.hang_up` |
   | `missing_to_submit` | `from app.seniors import service` inside `submit_senior()`; `tests/test_enrollments.py` patches `app.seniors.service.missing_to_submit` | imported at the top of `seniors/router.py`; the test patches `app.seniors.router.missing_to_submit` |

6. **Knock-on edits:** 15 imports from a package facade in `tests/` and `scripts/`, counted 2026-10-16: `conftest.py`, `test_calls.py`, `test_enrollments.py`, `test_grants.py`, `test_incidents.py` (2), `test_incidents_api.py`, `test_models.py` (2), `test_relay.py`, `test_status.py`, `test_verify.py`, `test_voice.py`, `scripts/grant_das.py`, `scripts/place_call.py`. In `conftest.py`, `from app.auth import bearer, refuse, verify_token` becomes `app.auth.service`; `app.dependency_overrides[verify_token]` keys on the function object, which is the same object whichever path imports it.

## 5. Naming

| Kind | Lives in | Name | Examples |
|---|---|---|---|
| ORM table | `models.py` | the plain noun | `Senior`, `Call`, `CallTurn`, `StatusReport` |
| Pydantic request body | `schemas.py` | noun + `Form` | `SeniorForm`, `CaregiverForm` |
| Pydantic response, or a part of one | `schemas.py` | noun + `View` (one item for a role), `Summary` (a list row or a short form), or `Detail` (a full single read) | `SeniorView`, `IncidentSummary`, `CallDetail` |
| Value object in pure logic | its logic module | the plain noun, as a frozen dataclass | `Answer`, `AlarmMatch` |

Renames (the JSON stays the same; only schema titles in `/api/openapi.json` change. Neither the dashboard nor Android generates code from that file, checked 2026-10-16):

| Today | After | Kind |
|---|---|---|
| `Me` | `MeView` | response, `GET /api/me` |
| `StaffGrant` | `StaffGrantForm` | request body |
| `StaffMember` | `StaffMemberView` | response |
| `StaffListing` | `StaffListingView` | response |
| `Caregiver` | `CaregiverSummary` | part of a response; `CaregiverView` becomes `CaregiverView(CaregiverSummary)` |
| `Resolution` | `ResolutionForm` | request body |
| `TriggerEvent` | `TriggerEventView` | part of a response |
| `Turn` | `TurnView` | part of a response |
| `Report` | `ReportView` | part of a response |
| `DatabaseHealth` | `DatabaseHealthView` | part of a response |
| `SystemHealth` | `SystemHealthView` | response |

Already conforming, unchanged: `GrantView`, `CaregiverView`, `MedicView`, `SeniorDetail`, `SeniorForm`, `CaregiverForm`, `SeniorSummary`, `SeniorView`, `IncidentSummary`, `CallDetail`, `IncidentDetail`. `Note` is a field type (`Annotated[str, …]`), not a class, and keeps its name.

The two `Answer` classes keep their names: `voice.models.Answer` is the ORM table and `status.engine.Answer` is the engine's value object. A module that needs both imports the engine by module (`from app.status import engine`, then `engine.Answer`).

## 6. Enforcement: import-linter

Dev dependency `import-linter` 2.15 (supports Python 3.14, released 2026-09-04): `uv add --dev import-linter`. Contracts in `backend/pyproject.toml`:

```toml
[tool.importlinter]
root_package = "app"
include_external_packages = true

# Wildcards, not lists, so a new package under app/ is held to every contract (spec §10).

[[tool.importlinter.contracts]]
name = "Inside a feature: router, then service, then schemas, then models"
type = "layers"
containers = ["app.*"]
layers = ["(router)", "(service)", "(schemas)", "(models)"]

[[tool.importlinter.contracts]]
name = "Only app.main imports a router"
type = "protected"
protected_modules = ["app.*.router"]
allowed_importers = ["app.main"]

[[tool.importlinter.contracts]]
name = "Package __init__ files import nothing; app.models is the one aggregator"
type = "forbidden"
source_modules = ["app", "app.*"]
forbidden_modules = ["app.**"]
as_packages = false
# app.* also matches these two, which are modules that import by design.
ignore_imports = ["app.main -> app.**", "app.models -> app.**"]

[[tool.importlinter.contracts]]
name = "The status engine is pure logic (01 §8)"
type = "forbidden"
source_modules = ["app.status"]
forbidden_modules = ["fastapi", "httpx", "sqlalchemy", "app.*"]

[[tool.importlinter.contracts]]
name = "app.models is for Alembic, scripts and tests, not for app/"
type = "forbidden"
source_modules = ["app.*"]
forbidden_modules = ["app.models"]

[[tool.importlinter.contracts]]
name = "No import cycles between packages; routers sit above them all"
type = "acyclic_siblings"
ancestors = ["app"]
depth = 0
ignore_imports = ["app.*.router -> app.**"]
```

| Contract | What it stops |
|---|---|
| Layers | a schema importing a service, a model importing a router |
| Only `app.main` imports a router | router-to-router imports; a facade loading its router |
| `__init__` files import nothing | re-exports coming back. It is needed because import-linter records explicit imports only: the implicit run of `__init__.py` behind `import app.voice.models` is not an edge, so the layers contract alone would not have caught problem 3 |
| Pure status engine | the engine picking up a database, web or HTTP dependency, against `01 §8` |
| `app.models` outside `app/` only | going back to the global aggregator inside the app |
| No cycles between packages | e.g. `seniors` ↔ `incidents`. Routers' outgoing imports are excluded because routers are the top layer and nothing imports them; this is what lets `/me` in `auth.router` read seniors |

The contracts name packages with wildcards (`app.*`), not lists, so a package added later is held to all six without editing them; `tests/test_contracts.py` plants a violation in a new package and checks each contract still catches it. Every layer is optional, because a package such as `core` or `status` has no router.

The contract set is a starting point: if a contract fails on the finished code for a reason this design did not foresee, fix the code when the code is wrong, and change the contract only when the design is.

`uv run lint-imports` runs in:

- `.github/workflows/backend.yml`, after `ruff format --check`;
- the `backend` group in `lefthook.yml` `pre-commit`, after `ruff format` and before `pytest`;
- the command tables in `backend/AGENTS.md` and `backend/README.md` ("Test and lint").

## 7. Docs

`backend/AGENTS.md`:

- the layout tree matches §3, including `system/`, `core/storage.py` and the file roles;
- three new rules: the import rule (§4), the file roles and names for ORM and Pydantic (§3.1, §5), and "run `uv run lint-imports`; don't loosen a contract to make it pass";
- `lint-imports` in the commands table, and the CI line updated to say CI runs five commands, not four.

`backend/README.md`: add `lint-imports` to "Test and lint".

## 8. Verification

Take a baseline before the first change:

1. `uv run pytest`: record the number of passing tests.
2. Dump the OpenAPI document: `uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), sort_keys=True))"`, saved to a scratch directory outside the repository.

After the last change:

1. `uv run ruff check .`, `uv run ruff format --check .` and `uv run lint-imports` are clean.
2. `uv run pytest` passes the same number of tests.
3. In fresh interpreters, `python -c "import app.models"` and `python -c "import app.voice.models"` succeed: the import orders that broke in problem 3.
4. OpenAPI comparison: the same paths and methods, and every request and response schema structurally identical once the 11 renames in §5 are applied to component names and `$ref`s. The only allowed difference is schema titles.
5. `docker compose exec api alembic check` reports no new upgrade operations, so the aggregator still sees every table.
6. `lefthook run pre-commit` passes.
7. `grep -rnE '^[[:space:]]+(from|import) app' backend/app` finds nothing (no imports inside functions). On 2026-10-16 it finds the four in §4.

## 9. Rollout

One PR from branch `backend-layout`, with one commit per step, each passing ruff and pytest:

1. **Guard rails.** Add import-linter and the contracts from §6, not yet wired into CI or the hook. Three contracts fail on today's code; that is the red test for step 2.
2. **Imports.** Empty the package `__init__.py` files, switch `app/`, `scripts/` and `tests/` to direct imports, move the function-level imports to the top, and update the two test seams. All six contracts pass from here on.
3. **Schemas.** Add `schemas.py` to each package, move the Pydantic classes, apply the renames, rename `system/models.py`.
4. **Services.** Move `incidents/views.py` and the router helpers into `incidents/service.py`, add `voice/service.py` with `move_call`, move `/api/health` into `system/router.py`, delete the `main.py` re-exports.
5. **Enforcement and docs.** Run `lint-imports` in CI and the hook, and update the docs.

Imports come before schemas so that the moves in steps 3 and 4 never have to keep a facade's re-exports in sync.

API changes only add (ADR-001 §2.3): this change adds nothing and removes nothing from the API, and needs no migration. Merging to `main` redeploys staging's `api` and drops live calls (root `AGENTS.md`), so the merge waits for a moment with no test calls running.

## 10. Out of scope, noted

- Two near-identical `caregivers_query` functions (`seniors/service.py`, and `incidents/views.py`, which becomes `incidents/service.py`); the seniors one also selects `user_id`. Merging them changes a query and belongs in its own change.
- Services raise FastAPI's `HTTPException` through `auth.service.refuse`. This matters only once the dialer, the notifier or call sessions become separate workers (`01 §8`).
- Homes for the `01 §8` modules still to come. Each new one follows §3.1: a package with the files it needs, held to the same contracts.
