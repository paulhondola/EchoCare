# Domain-Driven Architecture Restructuring Design

**Date**: 2026-10-13  
**Status**: Approved  
**Classification**: Architectural  
**Scope**: `backend/app/` and `dashboard/src/`

---

## 1. Context & Motivation

The Sentinela codebase currently maintains flat structures in both the backend (`backend/app/` with 16 files) and the DAS dashboard (`dashboard/src/` with 14 files). As new features arrive (e.g. enrollment workflows, Twilio Voice relay, incident handling, mobile integration), single files like `main.py` (625 lines) and `models.py` (526 lines) have accumulated disparate domain logic, routing, schemas, and queries.

This restructuring reorganizes both subsystems into **feature / domain-driven packages (vertical slices)**, isolating domain logic, routing, and models, while maintaining strict backward compatibility with Alembic migrations, existing scripts, and testing harnesses.

---

## 2. Requirements & Constraints

1. **Vertical Domain Grouping**: Group code by business domain (e.g., `incidents`, `seniors`, `voice`, `auth`, `staff`, `status`), isolating domain routes, models, and services.
2. **Backward-Compatible Database Models**: Split SQLAlchemy models into their domain packages, but preserve `app.models` via `app/models/__init__.py` re-exports so Alembic (`import app.models`), migrations, and existing tests continue to work without disruption.
3. **Infrastructure Decoupling**: Isolate shared, non-domain infrastructure (`db`, `settings`, `phones`) in `app/core/` to prevent circular dependencies.
4. **Lean API Entrypoint**: Slim down `backend/app/main.py` to only initialize FastAPI, configure CORS and logging, register `/health`, and mount domain routers.
5. **Dashboard Feature Structure**: Organize `dashboard/src/` into `features/<domain>/`, `services/`, and `utils/`.
6. **Zero Breaking Changes to External Interfaces**: The REST and WebSocket API contract (`/api/...`) and user-facing behavior remain unchanged.
7. **Verification**: All backend tests (`pytest`), linters (`ruff`), dashboard type checks (`vp check`), and builds (`npm run build`) must pass cleanly.

---

## 3. Backend Architecture (`backend/app/`)

### 3.1 Target Layout

```
backend/app/
├── core/                       # Technical foundation (no domain dependencies)
│   ├── __init__.py
│   ├── db.py                   # Async SQLAlchemy engine, session maker, get_session, Base
│   ├── settings.py             # Settings, environment validation, Railway checks
│   └── phones.py               # E.164 normalization, mobile validation, masking
│
├── auth/                       # Authentication, callers, grants & /me
│   ├── __init__.py
│   ├── models.py               # User, Role, Grant models and enums
│   ├── service.py              # Firebase token verification, Caller dependency, require_roles
│   └── router.py               # GET /me route and schemas (Me, GrantView)
│
├── seniors/                    # Seniors, caregivers, and enrollment pipeline
│   ├── __init__.py
│   ├── models.py               # Senior, Caregiver, Consent models and enums
│   ├── service.py              # Queries (seniors, enrollments), validation, reach rules
│   └── router.py               # /seniors, /seniors/{id}/caregivers, /enrollments, submit, accept
│
├── incidents/                  # Emergency incidents and operator handoff
│   ├── __init__.py
│   ├── models.py               # Incident, IncidentEvent, IncidentOutcome models and enums
│   ├── service.py              # Lifecycle transitions (take, resolve), refusals
│   ├── views.py                # Composite incident detail loader (former incident_view.py)
│   └── router.py               # GET /incidents, GET /incidents/{id}, /take, /resolve
│
├── voice/                      # Telephony edge, Twilio integration & call relay
│   ├── __init__.py
│   ├── models.py               # Call, CallTurn, Campaign models and enums
│   ├── calls.py                # Call states (LIVE, completed, machine detection)
│   ├── twilio.py               # Twilio Voice API, webhook signature checks
│   ├── relay.py                # ConversationRelay WebSocket handler & dialogue turns
│   └── router.py               # Twilio callback webhooks & WS routes
│
├── status/                     # Status engine & alarm phrase processing
│   ├── __init__.py
│   ├── engine.py               # Severity, Certainty, matrix rules, combining engine
│   └── alarms.py               # Romanian alarm phrase normalization and tier classification
│
├── staff/                      # Staff management (DAS and medic accounts)
│   ├── __init__.py
│   ├── service.py              # grant_staff, user_for lookups
│   └── router.py               # GET /staff, POST /staff
│
├── models/                     # Compatibility package for Alembic & tests
│   └── __init__.py             # Re-exports all tables & enums from domain models
│
└── main.py                     # App setup, CORS, /api/health, and router mounts
```

### 3.2 Symbol and File Migration Map

| Existing Source File | Destination | Key Classes & Functions |
|---|---|---|
| `db.py` | `core/db.py` | `Base`, `engine`, `Session`, `get_session` |
| `settings.py` | `core/settings.py` | `Settings`, `get_settings`, `check_environment`, `is_local_db`, `on_railway`, `db_host` |
| `phones.py` | `core/phones.py` | `normalize`, `is_mobile`, `mask` |
| `auth.py` | `auth/service.py` | `Caller`, `current_caller`, `require_roles`, `refuse`, `verify_token`, `bearer` |
| `main.py` (auth routes) | `auth/router.py` | `router`, `Me`, `GrantView`, `GET /me` |
| `models.py` (auth) | `auth/models.py` | `User`, `Role`, `ROLE_ORDER`, `SENIOR_ROLES`, `Grant` |
| `staff.py` | `staff/service.py` | `grant_staff`, `user_for` |
| `main.py` (staff routes) | `staff/router.py` | `router`, `StaffGrant`, `StaffMember`, `GET /staff`, `POST /staff` |
| `seniors.py` | `seniors/service.py` | `SeniorForm`, `CaregiverForm`, `SeniorView`, `SeniorSummary`, `CaregiverView`, `seniors_query`, `enrollments_query`, `sync_senior_grant` |
| `main.py` (seniors routes) | `seniors/router.py` | `router`, `GET /seniors`, `POST /seniors`, `PUT /seniors/{id}`, `POST /seniors/{id}/caregivers`, `DELETE /seniors/{id}/caregivers/{user_id}`, `POST /seniors/{id}/submit`, `POST /seniors/{id}/accept`, `GET /enrollments` |
| `models.py` (seniors) | `seniors/models.py` | `Senior`, `Caregiver`, `Consent`, `EnrollmentState`, `ConsentDecision`, `ConsentMethod` |
| `incidents.py` | `incidents/service.py` | `take_refusal`, `resolve_refusal` |
| `incident_view.py` | `incidents/views.py` | `IncidentDetail`, `load_incident`, `incident_query`, `caregivers_query`, `calls_query` |
| `main.py` (incidents routes) | `incidents/router.py` | `router`, `Resolution`, `IncidentSummary`, `incidents_query`, `parse_statuses`, `GET /incidents`, `GET /incidents/{id}`, `POST /incidents/{id}/take`, `POST /incidents/{id}/resolve` |
| `models.py` (incidents) | `incidents/models.py` | `Incident`, `IncidentEvent`, `IncidentStatus`, `IncidentOutcome`, `UNRESOLVED` |
| `calls.py` | `voice/calls.py` | `CallState`, `LIVE`, `after_callback`, `answered_by_machine` |
| `twilio.py` | `voice/twilio.py` | `dial`, `hangup`, `signature`, `signed`, `public_url` |
| `voice.py` | `voice/relay.py` + `voice/router.py` | `Relay`, `greeting`, `GOODBYE`, Twilio callback endpoints, WS relay endpoint |
| `models.py` (voice) | `voice/models.py` | `Campaign`, `Call`, `CallTurn`, `CallTrigger`, `CallDirection`, `Speaker`, `TurnKind` |
| `status.py` | `status/engine.py` | `Severity`, `Certainty`, `Question`, `combine_statuses`, `evaluate_status` |
| `alarms.py` | `status/alarms.py` | `Tier`, `check`, `confirmation_question`, `needs_help`, `normalize` |

### 3.3 Database Models & Alembic Compatibility

`backend/app/models/__init__.py` will import and re-export all models and enums:
```python
from app.auth.models import Role, ROLE_ORDER, SENIOR_ROLES, User, Grant
from app.seniors.models import EnrollmentState, ConsentDecision, ConsentMethod, Senior, Caregiver, Consent
from app.incidents.models import IncidentStatus, IncidentOutcome, UNRESOLVED, Incident, IncidentEvent
from app.voice.models import CallTrigger, CallDirection, Campaign, Call, Speaker, TurnKind, CallTurn

__all__ = [
    "Role", "ROLE_ORDER", "SENIOR_ROLES", "User", "Grant",
    "EnrollmentState", "ConsentDecision", "ConsentMethod", "Senior", "Caregiver", "Consent",
    "IncidentStatus", "IncidentOutcome", "UNRESOLVED", "Incident", "IncidentEvent",
    "CallTrigger", "CallDirection", "Campaign", "Call", "Speaker", "TurnKind", "CallTurn",
]
```
Because `alembic/env.py` performs `import app.models`, this ensures `target_metadata = Base.metadata` tracks all tables without any change to Alembic config.

### 3.4 Aggregator Entrypoint (`main.py`)

`backend/app/main.py` will:
1. Initialize settings and logging (`sentinela`, `sentinela.incidents`).
2. Run environment validation via `check_environment(settings)`.
3. Create `FastAPI(docs_url="/api/docs", ...)` with `CORSMiddleware`.
4. Create `api = APIRouter(prefix="/api")` and attach `/health`.
5. Mount domain routers:
   ```python
   api.include_router(auth_router)
   api.include_router(staff_router)
   api.include_router(seniors_router)
   api.include_router(incidents_router)
   api.include_router(voice_router)
   app.include_router(api)
   ```

---

## 4. Dashboard Architecture (`dashboard/src/`)

### 4.1 Target Layout

```
dashboard/src/
├── features/
│   ├── auth/
│   │   ├── SignIn.tsx            # Firebase phone auth form & invisible reCAPTCHA
│   │   └── index.ts              # Export SignIn
│   ├── incidents/
│   │   ├── IncidentBoard.tsx     # Incident board with status columns
│   │   ├── IncidentCard.tsx      # Incident action card (Preiau, Rezolvă)
│   │   ├── IncidentDetails.tsx   # Detailed modal with timeline & caregiver contacts
│   │   └── index.ts              # Exports
│   ├── enrollments/
│   │   ├── Enrollments.tsx       # Applications table and Acceptă modal
│   │   └── index.ts              # Exports
│   └── staff/
│       ├── Staff.tsx             # Staff list and medic/DAS role creation
│       └── index.ts              # Exports
│
├── services/                     # External API & third-party service clients
│   ├── api.ts                    # Backend API client, token refresh, typed endpoints
│   └── firebase.ts               # Firebase App & Auth client initialization
│
├── utils/                        # Shared utilities & formatters
│   ├── phone.ts                  # E.164 phone formatting & validation
│   ├── phone.test.ts             # Vitest unit tests for phone formatting
│   └── labels.ts                 # Romanian UI strings, date & address formatting
│
├── App.tsx                       # Root view switcher, Firebase auth state, tab layout
├── main.tsx                      # React root rendering
└── styles.css                    # Tailwind v4 + DaisyUI 5 style entry
```

### 4.2 Module Migration Map

| Existing Source File | Destination | Description |
|---|---|---|
| `SignIn.tsx` | `features/auth/SignIn.tsx` | Phone auth form |
| `IncidentBoard.tsx` | `features/incidents/IncidentBoard.tsx` | Status column board |
| `IncidentCard.tsx` | `features/incidents/IncidentCard.tsx` | Card with state actions |
| `IncidentDetails.tsx` | `features/incidents/IncidentDetails.tsx` | Detailed view modal |
| `Enrollments.tsx` | `features/enrollments/Enrollments.tsx` | Enrollment table |
| `Staff.tsx` | `features/staff/Staff.tsx` | Staff administration |
| `api.ts` | `services/api.ts` | API client & contracts |
| `firebase.ts` | `services/firebase.ts` | Firebase setup |
| `phone.ts` | `utils/phone.ts` | Phone validation helper |
| `phone.test.ts` | `utils/phone.test.ts` | Phone helper tests |
| `labels.ts` | `utils/labels.ts` | Shared labels & date formats |

---

## 5. Verification Plan

1. **Backend Verification**:
   - `uv run ruff check .` and `uv run ruff format --check .` in `backend/`.
   - `uv run python -c "import app.models; import app.main"` to verify imports and registration.
   - `uv run pytest` to ensure all 18 test files pass with 0 regressions.
2. **Dashboard Verification**:
   - `npx vp check` in `dashboard/` to verify linting, formatting, and TypeScript types.
   - `npm run build` in `dashboard/` to verify production bundle compilation.
3. **Pre-commit Git Hook Verification**:
   - `lefthook run pre-commit` from repository root.
4. **Documentation Updates**:
   - Update layout diagrams in `backend/AGENTS.md` and `dashboard/AGENTS.md`.
