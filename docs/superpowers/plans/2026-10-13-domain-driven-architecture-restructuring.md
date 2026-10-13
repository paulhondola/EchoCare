# Domain-Driven Architecture Restructuring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `backend/app/` and `dashboard/src/` from flat directories into vertical feature/domain packages with modular routes, models, services, and components while preserving full compatibility with Alembic and tests.

**Architecture:** Vertical slice / domain-driven modularization. Backend modules group their own models, services, and FastAPI routers under `app/<domain>/`, with `app/core/` for technical infrastructure, `app/models/__init__.py` for central table registration, and a lean `app/main.py` aggregator. Frontend modules group views into `src/features/<domain>/`, with dedicated `src/services/` and `src/utils/`.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 (asyncpg), Alembic, Pydantic v2, pytest, React 19, TypeScript, Vite+.

**Spec:** `docs/superpowers/specs/2026-10-13-domain-driven-architecture-restructuring-design.md`

## Global Constraints

- **Python version**: Python 3.14 via `uv`.
- **FastAPI routes**: All API routes must remain prefixed under `/api` (`APIRouter(prefix="/api")`).
- **Alembic table discovery**: `import app.models` must register all tables with `app.core.db.Base.metadata`.
- **Database mutations**: No schema changes or migrations; pure code and file restructuring.
- **Frontend toolchain**: Vite+ (`npx vp check`), Tailwind v4, DaisyUI 5.
- **Git hooks**: All changes must pass `lefthook run pre-commit`.

## Review Focus

1. **Alembic autogenerate breakage**: If a domain model isn't imported into `app/models/__init__.py`, Alembic will fail to see the table and attempt to drop it on next autogenerate.
2. **Circular imports between domain models**: `incidents` references `seniors` and `users`; `seniors` references `users`. Models must rely on string foreign keys (e.g. `ForeignKey("users.id")`) rather than direct model class imports.
3. **Route registration order**: `app.include_router(api)` in `main.py` must only occur after all domain routers are attached to `api`.
4. **Script & test import breakages**: Standalone scripts (`grant_das.py`, `place_call.py`) and tests importing from legacy paths must be updated or supported by re-export modules.
5. **Dashboard relative imports**: Moving components to `features/<domain>/` must update imports to `../../services/api` and `../../utils/labels` without broken relative paths.

---

### Task 1: Backend `app/core/` Foundation

**Files:**
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/db.py`
- Create: `backend/app/core/settings.py`
- Create: `backend/app/core/phones.py`
- Modify: `backend/app/db.py` (shim re-export)
- Modify: `backend/app/settings.py` (shim re-export)
- Modify: `backend/app/phones.py` (shim re-export)

**Interfaces:**
- Consumes: Standard libraries, `sqlalchemy.ext.asyncio`, `pydantic_settings`.
- Produces: `app.core.db.{Base, engine, Session, get_session}`, `app.core.settings.{Settings, get_settings, check_environment}`, `app.core.phones.{normalize, is_mobile, mask}`.

- [ ] **Step 1: Create `backend/app/core/` directory and populate `db.py`, `settings.py`, and `phones.py`**

Move logic from `backend/app/db.py`, `backend/app/settings.py`, and `backend/app/phones.py` into `backend/app/core/`.
Update internal imports inside `core/settings.py` and `core/db.py` to point to `app.core.*`.

- [ ] **Step 2: Add backward-compatibility re-exports in legacy `app/db.py`, `app/settings.py`, `app/phones.py`**

```python
# app/db.py
from app.core.db import Base, Session, engine, get_session  # noqa: F401

__all__ = ["Base", "Session", "engine", "get_session"]
```

- [ ] **Step 3: Run existing core unit tests**

Run: `uv run pytest tests/test_settings.py tests/test_phones.py` in `backend/`.
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/ backend/app/db.py backend/app/settings.py backend/app/phones.py
git commit -m "refactor(backend): extract app.core foundation package"
```

---

### Task 2: Backend `app/auth/` & `app/staff/` Domains

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/models.py`
- Create: `backend/app/auth/service.py`
- Create: `backend/app/auth/router.py`
- Create: `backend/app/staff/__init__.py`
- Create: `backend/app/staff/service.py`
- Create: `backend/app/staff/router.py`
- Modify: `backend/app/auth.py` (shim re-export)
- Modify: `backend/app/staff.py` (shim re-export)

**Interfaces:**
- Consumes: `app.core.db`, `app.core.settings`, `app.core.phones`.
- Produces:
  - `app.auth.models`: `Role`, `ROLE_ORDER`, `SENIOR_ROLES`, `User`, `Grant`.
  - `app.auth.service`: `Caller`, `current_caller`, `require_roles`, `refuse`, `verify_token`, `bearer`.
  - `app.auth.router`: `router` with `GET /me`.
  - `app.staff.service`: `grant_staff`, `user_for`.
  - `app.staff.router`: `router` with `GET /staff`, `POST /staff`.

- [ ] **Step 1: Extract `app/auth/models.py`**

Extract `Role`, `ROLE_ORDER`, `SENIOR_ROLES`, `User`, `Grant` from `models.py` into `backend/app/auth/models.py`, inheriting from `app.core.db.Base`.

- [ ] **Step 2: Extract `app/auth/service.py` and `app/auth/router.py`**

Move caller verification and auth helpers from `app/auth.py` to `app/auth/service.py`.
Extract `Me`, `GrantView`, and `@api.get("/me")` from `app/main.py` into `app/auth/router.py`.
Re-export service symbols in `app/auth.py` and `app/auth/__init__.py`.

- [ ] **Step 3: Extract `app/staff/service.py` and `app/staff/router.py`**

Move `grant_staff`, `user_for` from `app/staff.py` to `app/staff/service.py`.
Extract `StaffGrant`, `StaffMember`, `@api.post("/staff")`, `@api.get("/staff")` from `app/main.py` into `app/staff/router.py`.
Re-export service symbols in `app/staff.py` and `app/staff/__init__.py`.

- [ ] **Step 4: Run auth and staff unit tests**

Run: `uv run pytest tests/test_me.py tests/test_staff.py tests/test_verify.py` in `backend/`.
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/ backend/app/staff/ backend/app/auth.py backend/app/staff.py
git commit -m "refactor(backend): modularize auth and staff domains"
```

---

### Task 3: Backend `app/status/` Domain

**Files:**
- Create: `backend/app/status/__init__.py`
- Create: `backend/app/status/engine.py`
- Create: `backend/app/status/alarms.py`
- Modify: `backend/app/status.py` (shim re-export)
- Modify: `backend/app/alarms.py` (shim re-export)

**Interfaces:**
- Consumes: Standard libraries.
- Produces:
  - `app.status.engine`: `Severity`, `Certainty`, `Question`, `combine_statuses`, `evaluate_status`.
  - `app.status.alarms`: `Tier`, `check`, `confirmation_question`, `needs_help`, `normalize`.

- [ ] **Step 1: Create `app/status/engine.py` and `app/status/alarms.py`**

Move logic from `app/status.py` to `app/status/engine.py`.
Move logic from `app/alarms.py` to `app/status/alarms.py`.
Update `app/status/__init__.py` to re-export `Severity`, `Certainty`, `Question`, `combine_statuses`.

- [ ] **Step 2: Update legacy shims `app/status.py` and `app/alarms.py`**

Re-export from `app.status.engine` and `app.status.alarms`.

- [ ] **Step 3: Run status and alarms unit tests**

Run: `uv run pytest tests/test_status.py tests/test_alarms.py` in `backend/`.
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/status/ backend/app/status.py backend/app/alarms.py
git commit -m "refactor(backend): modularize status and alarms domain"
```

---

### Task 4: Backend `app/voice/` Domain

**Files:**
- Create: `backend/app/voice/__init__.py`
- Create: `backend/app/voice/models.py`
- Create: `backend/app/voice/calls.py`
- Create: `backend/app/voice/twilio.py`
- Create: `backend/app/voice/relay.py`
- Create: `backend/app/voice/router.py`
- Modify: `backend/app/calls.py` (shim re-export)
- Modify: `backend/app/twilio.py` (shim re-export)
- Modify: `backend/app/voice.py` (shim re-export)

**Interfaces:**
- Consumes: `app.core`, `app.status`.
- Produces:
  - `app.voice.models`: `Campaign`, `Call`, `CallTurn`, `CallTrigger`, `CallDirection`, `Speaker`, `TurnKind`.
  - `app.voice.calls`: `CallState`, `LIVE`, `after_callback`, `answered_by_machine`.
  - `app.voice.twilio`: `dial`, `hangup`, `signature`, `signed`, `public_url`.
  - `app.voice.relay`: `Relay`, `greeting`, `GOODBYE`.
  - `app.voice.router`: `router` with Twilio callback and WebSocket endpoints.

- [ ] **Step 1: Extract `app/voice/models.py`**

Move `Campaign`, `Call`, `CallTurn`, `CallTrigger`, `CallDirection`, `Speaker`, `TurnKind` from `models.py` to `backend/app/voice/models.py`.

- [ ] **Step 2: Move calls, twilio, relay, router to `app/voice/`**

Move `calls.py` to `app/voice/calls.py`.
Move `twilio.py` to `app/voice/twilio.py`.
Split existing `voice.py` into `app/voice/relay.py` (Relay class, conversation logic) and `app/voice/router.py` (FastAPI router with `@router.post("/calls/incoming")`, etc.).

- [ ] **Step 3: Update legacy shims `app/calls.py`, `app/twilio.py`, `app/voice.py`**

Re-export from `app.voice.*`.

- [ ] **Step 4: Run voice and relay tests**

Run: `uv run pytest tests/test_calls.py tests/test_relay.py tests/test_voice.py` in `backend/`.
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/voice/ backend/app/calls.py backend/app/twilio.py backend/app/voice.py
git commit -m "refactor(backend): modularize telephony and voice domain"
```

---

### Task 5: Backend `app/seniors/` & `app/incidents/` Domains

**Files:**
- Create: `backend/app/seniors/__init__.py`
- Create: `backend/app/seniors/models.py`
- Create: `backend/app/seniors/service.py`
- Create: `backend/app/seniors/router.py`
- Create: `backend/app/incidents/__init__.py`
- Create: `backend/app/incidents/models.py`
- Create: `backend/app/incidents/service.py`
- Create: `backend/app/incidents/views.py`
- Create: `backend/app/incidents/router.py`
- Modify: `backend/app/seniors.py` (shim re-export)
- Modify: `backend/app/incidents.py` (shim re-export)
- Modify: `backend/app/incident_view.py` (shim re-export)

**Interfaces:**
- Consumes: `app.core`, `app.auth`.
- Produces:
  - `app.seniors.models`: `Senior`, `Caregiver`, `Consent`, `EnrollmentState`, `ConsentDecision`, `ConsentMethod`.
  - `app.seniors.service`: `SeniorForm`, `CaregiverForm`, `SeniorView`, `SeniorSummary`, `CaregiverView`, queries, access checks.
  - `app.seniors.router`: `router` with `/seniors`, `/seniors/{id}`, `/seniors/{id}/caregivers`, `/enrollments`, submit, accept.
  - `app.incidents.models`: `Incident`, `IncidentEvent`, `IncidentStatus`, `IncidentOutcome`, `UNRESOLVED`.
  - `app.incidents.service`: `take_refusal`, `resolve_refusal`.
  - `app.incidents.views`: `IncidentDetail`, `load_incident`, queries.
  - `app.incidents.router`: `router` with `/incidents`, `/incidents/{id}`, `/take`, `/resolve`.

- [ ] **Step 1: Extract `app/seniors/` package**

Move senior models from `models.py` to `app/seniors/models.py`.
Move logic from `app/seniors.py` to `app/seniors/service.py`.
Extract senior and enrollment endpoints from `app/main.py` into `app/seniors/router.py`.
Re-export in `app/seniors.py` shim.

- [ ] **Step 2: Extract `app/incidents/` package**

Move incident models from `models.py` to `app/incidents/models.py`.
Move lifecycle logic from `app/incidents.py` to `app/incidents/service.py`.
Move incident view loader from `app/incident_view.py` to `app/incidents/views.py`.
Extract incident endpoints from `app/main.py` into `app/incidents/router.py`.
Re-export in `app/incidents.py` and `app/incident_view.py` shims.

- [ ] **Step 3: Run senior and incident tests**

Run: `uv run pytest tests/test_seniors.py tests/test_enrollments.py tests/test_incidents.py tests/test_incidents_api.py tests/test_incident_view.py` in `backend/`.
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/seniors/ backend/app/incidents/ backend/app/seniors.py backend/app/incidents.py backend/app/incident_view.py
git commit -m "refactor(backend): modularize seniors and incidents domains"
```

---

### Task 6: Backend Central Models Package (`app/models/__init__.py`)

**Files:**
- Create: `backend/app/models/__init__.py`
- Delete: `backend/app/models.py`

**Interfaces:**
- Consumes: `app.auth.models`, `app.seniors.models`, `app.incidents.models`, `app.voice.models`.
- Produces: `app.models` package re-exporting all models and enums matching the existing `app/models.py` public API.

- [ ] **Step 1: Create `backend/app/models/__init__.py` and remove `backend/app/models.py`**

Import and re-export all domain models:
```python
from app.auth.models import ROLE_ORDER, SENIOR_ROLES, Grant, Role, User
from app.incidents.models import UNRESOLVED, Incident, IncidentEvent, IncidentOutcome, IncidentStatus
from app.seniors.models import (
    Caregiver,
    Consent,
    ConsentDecision,
    ConsentMethod,
    EnrollmentState,
    Senior,
)
from app.voice.models import (
    Call,
    CallDirection,
    CallTrigger,
    CallTurn,
    Campaign,
    Speaker,
    TurnKind,
)

__all__ = [
    "Role", "ROLE_ORDER", "SENIOR_ROLES", "User", "Grant",
    "EnrollmentState", "ConsentDecision", "ConsentMethod", "Senior", "Caregiver", "Consent",
    "IncidentStatus", "IncidentOutcome", "UNRESOLVED", "Incident", "IncidentEvent",
    "CallTrigger", "CallDirection", "Campaign", "Call", "Speaker", "TurnKind", "CallTurn",
]
```

- [ ] **Step 2: Verify model registration and test suite**

Run: `uv run python -c "import app.models; from app.core.db import Base; assert len(Base.metadata.tables) == 9, f'Expected 9 tables, got {len(Base.metadata.tables)}'"` in `backend/`.
Run: `uv run pytest tests/test_models.py` in `backend/`.
Expected: 9 tables registered, tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/ backend/app/models.py
git commit -m "refactor(backend): replace monolithic models.py with re-export package"
```

---

### Task 7: Slim Down `main.py` & Clean Up Legacy Shims

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/scripts/` (update any internal imports to new structure)
- Modify: `backend/tests/` (update any internal imports where appropriate)
- Delete: Legacy shim files (`backend/app/auth.py`, `backend/app/seniors.py`, `backend/app/incidents.py`, `backend/app/incident_view.py`, `backend/app/calls.py`, `backend/app/twilio.py`, `backend/app/voice.py`, `backend/app/status.py`, `backend/app/alarms.py`, `backend/app/staff.py`, `backend/app/db.py`, `backend/app/settings.py`, `backend/app/phones.py`) once all internal imports are updated.

**Interfaces:**
- Consumes: `app.auth.router`, `app.staff.router`, `app.seniors.router`, `app.incidents.router`, `app.voice.router`, `app.core`.
- Produces: Lean `main.py` with FastAPI initialization, CORS, `/health`, and router mounts.

- [ ] **Step 1: Refactor `backend/app/main.py`**

Assemble all domain routers onto `api = APIRouter(prefix="/api")`:
```python
api.include_router(auth_router)
api.include_router(staff_router)
api.include_router(seniors_router)
api.include_router(incidents_router)
api.include_router(voice_router)
app.include_router(api)
```

- [ ] **Step 2: Update all tests and scripts to direct domain imports and remove shim files**

Remove legacy shims in `app/`. Update imports in `backend/tests/` and `backend/scripts/` to use `app.<domain>.*` or `app.core.*` or `app.models`.

- [ ] **Step 3: Run complete backend test suite and linting**

Run in `backend/`:
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest`
Expected: 0 errors, all 18 test suites PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/
git commit -m "refactor(backend): slim down main.py and finalize domain package imports"
```

---

### Task 8: Dashboard Feature Modularization (`dashboard/src/`)

**Files:**
- Create: `dashboard/src/features/auth/SignIn.tsx`, `dashboard/src/features/auth/index.ts`
- Create: `dashboard/src/features/incidents/IncidentBoard.tsx`, `IncidentCard.tsx`, `IncidentDetails.tsx`, `index.ts`
- Create: `dashboard/src/features/enrollments/Enrollments.tsx`, `index.ts`
- Create: `dashboard/src/features/staff/Staff.tsx`, `index.ts`
- Create: `dashboard/src/services/api.ts`, `dashboard/src/services/firebase.ts`
- Create: `dashboard/src/utils/phone.ts`, `dashboard/src/utils/phone.test.ts`, `dashboard/src/utils/labels.ts`
- Modify: `dashboard/src/App.tsx`
- Delete: flat files moved from `dashboard/src/` (`SignIn.tsx`, `IncidentBoard.tsx`, `IncidentCard.tsx`, `IncidentDetails.tsx`, `Enrollments.tsx`, `Staff.tsx`, `api.ts`, `firebase.ts`, `phone.ts`, `phone.test.ts`, `labels.ts`)

**Interfaces:**
- Consumes: React, DaisyUI, Tailwind.
- Produces: Modularized feature components, services, and utils.

- [ ] **Step 1: Move services and utils**

Move `api.ts` and `firebase.ts` to `dashboard/src/services/`.
Move `phone.ts`, `phone.test.ts`, and `labels.ts` to `dashboard/src/utils/`.

- [ ] **Step 2: Move feature components and create feature index barrels**

Move `SignIn.tsx` to `features/auth/SignIn.tsx`.
Move `IncidentBoard.tsx`, `IncidentCard.tsx`, `IncidentDetails.tsx` to `features/incidents/`.
Move `Enrollments.tsx` to `features/enrollments/`.
Move `Staff.tsx` to `features/staff/`.
Add `index.ts` barrel exports for each feature.
Update relative imports inside each component to point to `../../services/*` and `../../utils/*`.

- [ ] **Step 3: Update `App.tsx` imports**

Update `App.tsx` to import features from `./features/*`, `./services/*`, and `./utils/*`.

- [ ] **Step 4: Run dashboard linter, type check, and build**

Run in `dashboard/`:
- `npx vp check`
- `npx vp test` (or `npm test`)
- `npm run build`
Expected: 0 lint errors, type check clean, Vite production bundle generated in `dist/`.

- [ ] **Step 5: Commit**

```bash
git add dashboard/
git commit -m "refactor(dashboard): organize into features, services, and utils"
```

---

### Task 9: Documentation Updates & Git Hook Verification

**Files:**
- Modify: `backend/AGENTS.md`
- Modify: `dashboard/AGENTS.md`

- [ ] **Step 1: Update layout tree in `backend/AGENTS.md`**

Replace flat layout diagram with the new domain package tree (`core/`, `auth/`, `seniors/`, `incidents/`, `voice/`, `status/`, `staff/`, `models/`, `main.py`).

- [ ] **Step 2: Update layout tree in `dashboard/AGENTS.md`**

Replace flat layout diagram with the new structure (`features/`, `services/`, `utils/`, `App.tsx`).

- [ ] **Step 3: Run git pre-commit hook**

Run from repo root: `lefthook run pre-commit`.
Expected: All hooks pass.

- [ ] **Step 4: Commit**

```bash
git add backend/AGENTS.md dashboard/AGENTS.md
git commit -m "docs: update backend and dashboard layouts in AGENTS.md"
```
