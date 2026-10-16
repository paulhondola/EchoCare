# Backend layers and schemas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every backend feature package the same file roles (`models.py` ORM, `schemas.py` Pydantic, `service.py`, `router.py`), one import rule and suffix names for Pydantic classes, enforced by import-linter, with no behavior change.

**Architecture:** First, add import-linter's six contracts; three fail on today's code, and those failures are the red test. Then empty the package facades (contracts go green), move the Pydantic classes into `schemas.py` with their new names (an OpenAPI comparison shows only the renames changed), and move the queries into `service.py`. Finally, wire `lint-imports` into CI and the hook, and update the docs. Code moves verbatim: docstrings, comments and logger names stay, because docstrings appear in OpenAPI.

**Tech Stack:** Python 3.14, FastAPI, Pydantic 2, SQLAlchemy 2 async, pytest, ruff, uv, import-linter ≥ 2.15, lefthook, GitHub Actions.

**Spec:** [docs/superpowers/specs/2026-10-16-backend-layers-and-schemas-design.md](../specs/2026-10-16-backend-layers-and-schemas-design.md)

## Global Constraints

- No behavior change: endpoint paths, JSON shapes, the database and the migrations stay the same, and every existing test passes (spec §1).
- Import a name from the module that defines it. Package `__init__.py` files are empty; `app/core/__init__.py` keeps its docstring. Inside `app/`, nothing imports `app.models` (spec §4).
- No imports inside functions (spec §4.4).
- ORM classes only in `models.py`, Pydantic only in `schemas.py`. `schemas.py` imports only enums from `models.py`, never ORM classes (spec §3.1).
- Names: an ORM class is the plain noun; a Pydantic request body is `…Form`; a response is `…View`, `…Summary` or `…Detail` (spec §5).
- Move code verbatim: docstrings, comments and logger names (`sentinela.voice`, `sentinela.incidents`, `sentinela.seniors`) stay as they are.
- Commit with the hooks on; never pass `--no-verify` or `LEFTHOOK=0`. Don't push, merge or open a PR.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Work on branch `backend-layout`. Run commands from `backend/` unless a step says otherwise; the `git add` / `git commit` blocks are written for the repository root.
- Scratch files live outside the repository: `S="${TMPDIR:-/tmp}/sentinela-backend-layout"`; `mkdir -p "$S"` once.
- Tests need Postgres: `docker compose up -d db` from the repository root.

## Review Focus

1. `/api/health` must stay unauthenticated and must fail when the database is unreachable, because Railway uses it to hold back a broken deploy. No test covers it today; Task 4 adds two.
2. A module imported *first*, in a fresh interpreter, must load. Alembic starts at `app.models`, scripts at a single `app.<pkg>.models`. pytest always imports `app.main` first and hides order-dependent cycles, so Task 2 adds `tests/test_imports.py`.
3. A test that monkeypatches a name the router no longer looks up passes without testing anything. Task 2 makes the submit-race test assert its patch actually ran. `monkeypatch.setattr(module, name, …)` already raises when the name doesn't exist.
4. `scripts/place_call.py` (the S1 test call) is not imported by any test, so a broken import there would only show when someone runs it. Task 2 imports it in `tests/test_imports.py`.
5. OpenAPI must stay identical apart from the 11 class names, including descriptions taken from docstrings. Task 3 adds the comparison, and Tasks 4 and 5 run it again.

---

### Task 1: Guard rails and baseline

**Files:**
- Modify: `backend/pyproject.toml` (add the dev dependency and the `[tool.importlinter]` block at the end)
- Modify: `backend/uv.lock` (written by `uv add`)
- Scratch: `$S/pytest-before.txt`, `$S/openapi-before.json`

**Interfaces:**
- Produces: `uv run lint-imports` with the six contracts from spec §6; `$S/openapi-before.json`, the OpenAPI document of today's code; `$S/pytest-before.txt`, holding the baseline `N passed`, where N is the number later tasks add to.

- [ ] **Step 1: Record the test baseline**

Run: `uv run pytest -q 2>&1 | tail -1 | tee "$S/pytest-before.txt"`
Expected: `N passed in …s` and no failures. If anything fails, stop and report: the baseline must be green before anything moves.

- [ ] **Step 2: Record the OpenAPI baseline**

Run: `uv run python -c 'import json; from app.main import app; print(json.dumps(app.openapi(), sort_keys=True))' > "$S/openapi-before.json" && uv run python -c "import json,sys; d=json.load(open(sys.argv[1])); print(len(d['paths']), len(d['components']['schemas']))" "$S/openapi-before.json"`
Expected: `18 27`.

- [ ] **Step 3: Add the dependency**

Run: `uv add --dev "import-linter>=2.15"`
Expected: `pyproject.toml`'s `dev` group gains `import-linter>=2.15`, and `uv.lock` resolves version 2.15 or newer.

- [ ] **Step 4: Add the contracts**

Copy the whole TOML block from spec §6 to the end of `backend/pyproject.toml`, unchanged: `[tool.importlinter]` and the six `[[tool.importlinter.contracts]]` tables.

- [ ] **Step 5: Run the contracts and see three fail**

Run: `uv run lint-imports`
Expected: `Contracts: 3 kept, 3 broken.`, with these three BROKEN:
- `Only app.main imports a router`
- `Package __init__ files import nothing; app.models is the one aggregator`
- `app.models is for Alembic, scripts and tests, not for app/`

And these three KEPT: the layers contract, `The status engine is pure logic (01 §8)`, and `No import cycles between packages; routers sit above them all`. These are the failing tests for Task 2.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "build(backend): add import-linter with the layering contracts" -m "Three contracts fail until the package facades are emptied." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: One import rule

**Files:**
- Create: `backend/tests/test_imports.py`
- Modify (emptied to zero bytes): `backend/app/{auth,incidents,seniors,staff,status,system,voice}/__init__.py`
- Modify: `backend/app/auth/router.py:10`, `backend/app/voice/router.py:16,18,37,92,142-144,167`, `backend/app/seniors/router.py:14-29,181-183`
- Modify: `backend/tests/{conftest,test_calls,test_enrollments,test_grants,test_incidents,test_incidents_api,test_models,test_relay,test_status,test_verify,test_voice}.py`, `backend/scripts/grant_das.py`, `backend/scripts/place_call.py`

**Interfaces:**
- Consumes: `uv run lint-imports` (Task 1).
- Produces: no package facades. Every name is importable only from its defining module, e.g. `app.seniors.service.forms_of_address`, `app.auth.service.refuse`, `app.status.engine.Severity`. The test seams are `app.voice.router.hang_up` and `app.seniors.router.missing_to_submit`.

- [ ] **Step 1: Write the import-order test**

`backend/tests/test_imports.py`:

```python
"""Each entry module loads when it is the first import, in a fresh interpreter.

pytest itself always imports app.main first, which hides cycles that depend on import
order. Alembic starts at app.models, the scripts at one package's models.
"""

import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).parent.parent


@pytest.mark.parametrize(
    "module",
    [
        "app.main",
        "app.models",
        "app.auth.models",
        "app.incidents.models",
        "app.seniors.models",
        "app.voice.models",
        "scripts.place_call",
    ],
)
def test_imports_first(module):
    run = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
```

- [ ] **Step 2: Run it; it passes on today's code**

Run: `uv run pytest tests/test_imports.py -q`
Expected: `7 passed`. It pins today's behavior before anything changes.

- [ ] **Step 3: Make the submit-race test prove its patch runs**

In `tests/test_enrollments.py`, `test_removing_the_caregiver_during_a_submit`:
- add `paused = []` after `checked = …`;
- add `paused.append(senior.id)` in `slow_check` before the sleep;
- add a final assertion: `assert paused, "the patch never reached submit_senior"`.

The seam itself moves in Step 6.

- [ ] **Step 4: Empty the facades**

Truncate these seven files to zero bytes: `app/{auth,incidents,seniors,staff,status,system,voice}/__init__.py`. Leave `app/core/__init__.py` (a docstring) and `app/models/__init__.py` (the aggregator) as they are.

- [ ] **Step 5: Point the app's own imports at the defining modules**

| File | Change |
|---|---|
| `app/auth/router.py:10` | `from app.seniors import forms_of_address` → `from app.seniors.service import forms_of_address` |
| `app/voice/router.py:16` | `from app.auth import refuse` → `from app.auth.service import refuse` |
| `app/voice/router.py` imports | add `from app.seniors.models import Senior`; line 37 becomes `from app.voice.twilio import hang_up, public_url, signed, voice_url` |
| `app/voice/router.py:92`, `:167` | delete `from app.models import Senior` and the blank line after it |
| `app/voice/router.py:142-144` | delete `from app import voice` and its blank line; `await voice.hang_up(sid)` → `await hang_up(sid)` |
| `app/seniors/router.py:14-29` | add `missing_to_submit` to the `from app.seniors.service import (…)` list |
| `app/seniors/router.py:181-183` | delete `from app.seniors import service` and its blank line; `await service.missing_to_submit(` → `await missing_to_submit(` |

- [ ] **Step 6: Point the tests and scripts at the defining modules**

| File | Today | After |
|---|---|---|
| `tests/conftest.py` | `from app.auth import bearer, refuse, verify_token` | `from app.auth.service import bearer, refuse, verify_token` |
| `tests/test_calls.py` | `from app.status import Certainty` | `from app.status.engine import Certainty` |
| `tests/test_enrollments.py` | `from app.seniors import service`; `service.missing_to_submit` (2 uses) | `from app.seniors import router as seniors_router`; `seniors_router.missing_to_submit` |
| `tests/test_grants.py` | `from app.staff import user_for` | `from app.staff.service import user_for` |
| `tests/test_incidents.py` | `from app.incidents import (IncidentStatus, opens_incident, resolve_refusal, take_refusal)`; `from app.status import Severity` | `from app.incidents.models import IncidentStatus`; `from app.incidents.service import opens_incident, resolve_refusal, take_refusal`; `from app.status.engine import Severity` |
| `tests/test_incidents_api.py` | `from app.incidents import IncidentStatus, incidents_query, parse_statuses` | `from app.incidents.models import IncidentStatus`; `from app.incidents.router import incidents_query, parse_statuses` (Task 4 moves `incidents_query`) |
| `tests/test_models.py` | `from app.incidents import UNRESOLVED`; `from app.status import Severity` | `from app.incidents.models import UNRESOLVED`; `from app.status.engine import Severity` |
| `tests/test_relay.py` | `from app.voice import GOODBYE, Relay, greeting` | `from app.voice.dialogue import GOODBYE, Relay, greeting` |
| `tests/test_status.py` | `from app.status import (…10 names…)` | `from app.status.engine import (…)`, the same 10 names |
| `tests/test_verify.py` | `from app import auth`; `auth.verify_token(` (4 uses) | `from app.auth.service import verify_token`; `verify_token(` |
| `tests/test_voice.py` | `from app import voice`; `voice.relay(` (4 uses); `monkeypatch.setattr(voice, "hang_up", …)` (lines 129, 140) | `from app.voice import router as voice_router`; `voice_router.relay(`; `monkeypatch.setattr(voice_router, "hang_up", …)` |
| `scripts/grant_das.py` | `from app.staff import grant_staff` | `from app.staff.service import grant_staff` |
| `scripts/place_call.py` | `from app.status import Severity` | `from app.status.engine import Severity` |

Leave the imports from `app.models` in tests and scripts alone: the aggregator is meant for them.

- [ ] **Step 7: Verify**

Run: `grep -rnE '^[[:space:]]+(from|import) app' app`
Expected: no output.

Run: `uv run lint-imports`
Expected: `Contracts: 6 kept, 0 broken.`

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: ruff clean; `N+7 passed`, with N from `$S/pytest-before.txt`.

- [ ] **Step 8: Commit**

```bash
git add -A backend/app backend/tests backend/scripts
git commit -m "refactor(backend): import from the defining module; empty package __init__ files" -m "Spec §4. Removes the facade cycle app.models -> app.voice -> app.voice.router -> app.models and the four imports inside functions." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Pydantic schemas in `schemas.py`, with Form/View names

**Files:**
- Create: `backend/app/auth/schemas.py`, `backend/app/staff/schemas.py`, `backend/app/seniors/schemas.py`, `backend/app/incidents/schemas.py`
- Rename: `backend/app/system/models.py` → `backend/app/system/schemas.py` (`git mv`)
- Modify: `backend/app/auth/router.py`, `backend/app/staff/router.py`, `backend/app/seniors/service.py`, `backend/app/seniors/router.py`, `backend/app/incidents/router.py`, `backend/app/incidents/views.py`, `backend/app/system/router.py`
- Scratch: `$S/openapi_same.py`, `$S/openapi-after.json`

**Interfaces:**
- Consumes: `$S/openapi-before.json` (Task 1). If it's missing, regenerate it from the base commit: `git worktree add "$S/base" 40a13dd`, copy `backend/.env.example` to `$S/base/backend/.env`, run Task 1 Step 2's dump with `$S/base/backend` as the working directory, then `git worktree remove "$S/base"`.
- Produces (verbatim moves; renames in **bold**):
  - `app.auth.schemas`: `GrantView`, **`MeView`**
  - `app.staff.schemas`: `Name`, `Practice`, **`StaffGrantForm`**, **`StaffMemberView`**, **`StaffListingView`**
  - `app.seniors.schemas`: `SeniorDetail`, **`CaregiverSummary`**, `no_nul`, `text`, `State`, `OPTIONAL`, `SeniorForm`, `CaregiverForm`, `SeniorSummary`, `CaregiverView(CaregiverSummary)`, `MedicView`, `SeniorView`
  - `app.incidents.schemas`: `Level`, `Note`, `IncidentSummary`, **`ResolutionForm`**, **`TriggerEventView`**, **`TurnView`**, **`ReportView`**, `CallDetail`, `IncidentDetail`
  - `app.system.schemas`: **`DatabaseHealthView`**, **`SystemHealthView`**
  - `$S/openapi_same.py BEFORE AFTER`: prints `same` and exits 0 when the documents match once the renames are applied to BEFORE; otherwise prints a diff and exits 1.

- [ ] **Step 1: Write the OpenAPI comparison**

`$S/openapi_same.py` (scratch, not committed):

```python
"""Exit 0 when two OpenAPI dumps match, once spec §5's renames are applied to the first."""

import difflib
import json
import sys

RENAMES = {
    "Me": "MeView",
    "StaffGrant": "StaffGrantForm",
    "StaffMember": "StaffMemberView",
    "StaffListing": "StaffListingView",
    "Caregiver": "CaregiverSummary",
    "Resolution": "ResolutionForm",
    "TriggerEvent": "TriggerEventView",
    "Turn": "TurnView",
    "Report": "ReportView",
    "DatabaseHealth": "DatabaseHealthView",
    "SystemHealth": "SystemHealthView",
}
REF = "#/components/schemas/"


def renamed(node):
    if isinstance(node, list):
        return [renamed(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: renamed(value) for key, value in node.items()}
    name = node.get("$ref", "").removeprefix(REF)
    if name in RENAMES:
        node["$ref"] = REF + RENAMES[name]
    return node


before, after = (json.load(open(path)) for path in sys.argv[1:3])
before = renamed(before)
schemas = before["components"]["schemas"]
for old, new in RENAMES.items():
    schemas[new] = {**schemas.pop(old), "title": new}
if before == after:
    print("same")
    sys.exit(0)
a, b = (json.dumps(d, indent=1, sort_keys=True).splitlines() for d in (before, after))
print("\n".join(list(difflib.unified_diff(a, b, "before+renames", "after", lineterm=""))[:120]))
sys.exit(1)
```

- [ ] **Step 2: Run it; it fails on today's names**

Run: `uv run python -c 'import json; from app.main import app; print(json.dumps(app.openapi(), sort_keys=True))' > "$S/openapi-after.json" && uv run python "$S/openapi_same.py" "$S/openapi-before.json" "$S/openapi-after.json"`
Expected: exit 1, and a diff showing `"MeView"` and the other new names on the `before+renames` side only.

- [ ] **Step 3: Move the schemas, package by package**

For each package, move the classes and field types listed under Produces into the new `schemas.py`, verbatim with their docstrings and comments. Apply the renames at every use site, and import from `schemas.py` where they were used:
- **auth:** `GrantView` and `Me` (→ `MeView`) from `router.py`; the router builds and returns `MeView`.
- **staff:** `Name`, `Practice`, `StaffGrant` (→ `StaffGrantForm`), `StaffMember` (→ `StaffMemberView`), `StaffListing` (→ `StaffListingView`) from `router.py`. `STAFF_ROLES` stays in the router; it's a query constant.
- **seniors:** lines 25–167 of `service.py`: `SeniorDetail`, `Caregiver` (→ `CaregiverSummary`), `no_nul`, `text`, `State`, `OPTIONAL`, `SeniorForm`, `CaregiverForm`, `SeniorSummary`, `CaregiverView`, `MedicView`, `SeniorView`. `REQUIRED_TO_SUBMIT` stays in `service.py`, which now imports `CaregiverView, MedicView, SeniorForm, SeniorView` from `app.seniors.schemas`. `router.py` imports `CaregiverForm, CaregiverView, SeniorForm, SeniorSummary, SeniorView` from `app.seniors.schemas` instead of `app.seniors.service`.
- **incidents:** from `router.py`, `IncidentSummary`, `Note`, `Resolution` (→ `ResolutionForm`). From `views.py`, `Level`, `TriggerEvent` (→ `TriggerEventView`), `Turn` (→ `TurnView`), `Report` (→ `ReportView`), `CallDetail`, `IncidentDetail`. `views.py`'s mid-file `from app.seniors.service import Caregiver, SeniorDetail` (line 19) becomes `from app.seniors.schemas import CaregiverSummary, SeniorDetail` at the top of `incidents/schemas.py`. The query and loader functions stay in `views.py` for now (Task 4 moves them) and import the schemas.
- **system:** `git mv app/system/models.py app/system/schemas.py`; rename `DatabaseHealth` → `DatabaseHealthView` and `SystemHealth` → `SystemHealthView` there and in `router.py`. The patch target `app.system.router.check_database_health` in `tests/test_system_health.py` stays valid.

`ruff check --fix` (the pre-commit hook) removes imports the moves leave unused.

- [ ] **Step 4: Verify**

Run: `uv run python -c 'import json; from app.main import app; print(json.dumps(app.openapi(), sort_keys=True))' > "$S/openapi-after.json" && uv run python "$S/openapi_same.py" "$S/openapi-before.json" "$S/openapi-after.json"`
Expected: `same`.

Run: `grep -rln 'BaseModel' app`
Expected: exactly the five `schemas.py` files (auth, incidents, seniors, staff, system).

Run: `grep -n 'models import' app/*/schemas.py`
Expected: only `app/incidents/schemas.py`, importing enums (`IncidentOutcome`, `IncidentStatus`), never an ORM class.

Run: `uv run lint-imports && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: `Contracts: 6 kept, 0 broken.`; ruff clean; `N+7 passed`.

- [ ] **Step 5: Commit**

```bash
git add -A backend/app
git commit -m "refactor(backend): Pydantic schemas in schemas.py, with Form and View names" -m "Spec §3.1 and §5. OpenAPI is unchanged apart from 11 schema names; the JSON is the same." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Queries in `service.py`; `/api/health` in the system router

**Files:**
- Modify: `backend/app/incidents/service.py`, `backend/app/incidents/router.py`
- Delete: `backend/app/incidents/views.py` (`git rm`)
- Create: `backend/app/voice/service.py`
- Modify: `backend/app/voice/router.py`, `backend/app/system/router.py`, `backend/app/main.py`
- Test: `backend/tests/test_system_health.py` (2 new tests), `backend/tests/test_incident_view.py:8`, `backend/tests/test_incidents_api.py` (the import from Task 2)

**Interfaces:**
- Consumes: the `app.incidents.schemas` names (Task 3).
- Produces (signatures unchanged, moved verbatim):
  - `app.incidents.service`: `incident_query`, `calls_query`, `caregivers_query`, `attempts_behind`, `load_incident`, `call_detail(call, reports: list[ReportView], turns: list[TurnView]) -> CallDetail` (from `views.py`); `incidents_query(statuses: set[IncidentStatus] | None, incident_id: uuid.UUID | None = None) -> Select`, `incident_summary(session, incident_id) -> IncidentSummary`, `current_incident(session, incident_id) -> Incident` (from `router.py`). `opens_incident`, `take_refusal`, `resolve_refusal` stay.
  - `app.voice.service.move_call(session: AsyncSession, call_id: uuid.UUID, sid: str | None, new: CallState | None) -> CallState | None`, logging to `logging.getLogger("sentinela.voice")`.
  - `app.system.router.health() -> dict[str, str]` at `GET /health`, so the path stays `/api/health`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_system_health.py` (add `import pytest` and `from app.core.settings import get_settings` to its imports):

```python
async def test_health_is_open_and_reports_the_env(client):
    # Railway's health check signs in as nobody (06 §1).
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "env": get_settings().app_env}


async def test_health_fails_when_db_down(client):
    # A failing check holds back a broken deploy (06 §1).
    with (
        patch(
            "app.system.router.check_database_health",
            side_effect=OperationalError("mock", {}, Exception()),
        ),
        pytest.raises(OperationalError),
    ):
        await client.get("/api/health")
```

In `tests/test_incident_view.py:8`, import from `app.incidents.service` instead of `app.incidents.views`. In `tests/test_incidents_api.py`, import `incidents_query` from `app.incidents.service` and keep `parse_statuses` from `app.incidents.router`.

- [ ] **Step 2: Run them and see the expected failures**

Run: `uv run pytest tests/test_system_health.py tests/test_incident_view.py tests/test_incidents_api.py -q`
Expected:
- collection errors in `test_incident_view.py` and `test_incidents_api.py` (`ImportError`: the names aren't in `app.incidents.service` yet);
- `test_health_fails_when_db_down` FAILS with `DID NOT RAISE` (`main.py`'s health doesn't use `check_database_health` yet);
- `test_health_is_open_and_reports_the_env` passes, pinning today's behavior.

- [ ] **Step 3: Move the incident queries**

Move everything left in `views.py` (Task 3 already took the schemas) to the end of `incidents/service.py`, then `git rm app/incidents/views.py`. Move `incidents_query`, `incident_summary` and `current_incident` from `incidents/router.py` to `incidents/service.py`; the router imports them. `parse_statuses`, `RESOLVED_SHOWN` and `log` stay in the router.

- [ ] **Step 4: Move `move_call`**

Create `app/voice/service.py` with `move_call` moved verbatim from `voice/router.py`, and `log = logging.getLogger("sentinela.voice")`. `voice/router.py` imports `move_call` from `app.voice.service`; `twilio_params`, `Params` and `Db` stay in the router.

- [ ] **Step 5: Move `/api/health`**

From `app/main.py`, delete:
- the `@api.get("/health")` function;
- its now-unused imports (`from sqlalchemy import text`, `from app.core.db import engine`);
- the import of `incidents_query, parse_statuses` and those two names in `__all__`, leaving `__all__ = ["app"]`.

Add to `app/system/router.py`:

```python
@router.get("/health")
async def health() -> dict[str, str]:
    # Fails when the database is unreachable, so Railway holds back a broken deploy (06 §1).
    await check_database_health()
    return {"status": "ok", "env": settings.app_env}
```

Use a comment, not a docstring: a docstring would become the operation's description in OpenAPI. The function name `health` keeps the operation id `health_api_health_get`.

- [ ] **Step 6: Verify**

Run: `uv run pytest tests/test_system_health.py tests/test_incident_view.py tests/test_incidents_api.py -q`
Expected: all pass.

Run: `uv run python -c 'import json; from app.main import app; print(json.dumps(app.openapi(), sort_keys=True))' > "$S/openapi-after.json" && uv run python "$S/openapi_same.py" "$S/openapi-before.json" "$S/openapi-after.json"`
Expected: `same`.

Run: `uv run lint-imports && uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: `Contracts: 6 kept, 0 broken.`; ruff clean; `N+9 passed`.

- [ ] **Step 7: Commit**

```bash
git add -A backend/app backend/tests
git commit -m "refactor(backend): queries in service.py; /api/health in the system router" -m "Spec §3.2. incidents/views.py folds into incidents/service.py; voice gets a service.py for move_call." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Enforce, document, verify the whole branch

**Files:**
- Modify: `.github/workflows/backend.yml:44` (after `ruff format --check`)
- Modify: `lefthook.yml` (the `backend` group of `pre-commit`)
- Modify: `backend/AGENTS.md` (Layout, Commands, Rules), `backend/README.md` ("Test and lint")

**Interfaces:**
- Consumes: everything above.
- Produces: `lint-imports` gating CI and every commit that touches backend Python.

- [ ] **Step 1: Wire `lint-imports` in**

In `backend.yml`, add `- run: uv run lint-imports` between `uv run ruff format --check .` and `uv run pytest`. In `lefthook.yml`'s `backend` group, add the job `- run: uv run lint-imports` between the `ruff format` job and the `pytest` job (no `stage_fixed`; it changes no files).

- [ ] **Step 2: Update `backend/AGENTS.md`**

- **Layout:** replace the `app/` part of the tree with:

  ```
  ├── app/
  │   ├── main.py        assembly: logging, CORS, the /api router, mounts every router
  │   ├── core/          settings, async db engine/session, phone E.164 normalization, S3 storage
  │   ├── models/        the one ORM aggregator, for Alembic, scripts and tests; app/ never imports it
  │   ├── auth/          Firebase token verification, callers, grants, /me
  │   ├── staff/         staff roles (medic, DAS)
  │   ├── seniors/       seniors, caregivers, consents, enrollments
  │   ├── incidents/     incident lifecycle, refusal reasons, incident detail
  │   ├── voice/         Twilio signatures and dialing, call lifecycle, dialogue relay
  │   ├── system/        /api/health and the dashboard's system health
  │   └── status/        alarm phrases, status matrix and engine; pure logic
  ```

  and add right after the tree: "Each feature package uses the files it needs from: `models.py` (SQLAlchemy ORM tables and the enums they store), `schemas.py` (Pydantic bodies and responses), `service.py` (rules and queries), `router.py` (endpoints only). `__init__.py` files are empty."
- **Commands:** add the row `| Import contracts | uv run lint-imports |` after the format row, and change "runs the first four" to "runs the first five".
- **Rules:** add three bullets:
  - "**Import a name from the module that defines it.** No re-exports in `__init__.py`, no imports inside functions. Tests patch a name in the module that uses it."
  - "**ORM in `models.py`, Pydantic in `schemas.py`.** An ORM class is the plain noun (`Senior`); a Pydantic request body ends in `Form`, a response in `View`, `Summary` or `Detail`. `schemas.py` imports only enums from `models.py`."
  - "**`uv run lint-imports` must pass.** The contracts are in `pyproject.toml`. Fix the code, not the contract, unless the design changed (spec 2026-10-16 §6)."

- [ ] **Step 3: Update `backend/README.md`**

In "Test and lint", after the `ruff format` block, add a `uv run lint-imports` block, and say in one sentence that it checks the import contracts in `pyproject.toml`.

- [ ] **Step 4: Verify the whole branch (spec §8)**

From the repository root, start the stack: `docker compose up -d db api`. Then run each check below and compare with its expected result.

- `cd backend && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`: ruff clean; `Contracts: 6 kept, 0 broken.`
- `cd backend && uv run pytest -q`: `N+9 passed`, with N from `$S/pytest-before.txt`.
- In `backend/`, Task 3 Step 4's dump-and-compare command: `same`.
- `docker compose exec api alembic check`: `No new upgrade operations detected.`
- `grep -rnE '^[[:space:]]+(from|import) app' backend/app`: no output.
- `lefthook run pre-commit --all-files`: every backend job passes.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/backend.yml lefthook.yml backend/AGENTS.md backend/README.md
git commit -m "ci(backend): run lint-imports in CI and the pre-commit hook; document the layout" -m "Spec §6 and §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Don't push. Report the branch, the five commits and the verification results.
