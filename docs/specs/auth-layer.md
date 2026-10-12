# Auth layer

**Status:** approved design · 2026-10-11 · branch `auth-layer`
**Implements:** G6 and UC-02 (phone sign-in, grants), the API half of UC-14 (grant staff), [01 §6](sentinela/01-architecture.md), [04 §0, §1 `/me`, §2 `/staff`, §7](sentinela/04-interfaces.md), [06 §4](sentinela/06-operations.md) (access).
**Read with:** the system spec in [sentinela/](sentinela/README.md). Where the two disagree, this file wins for the auth layer, and slice 1 brings the system spec in line (§6.6).

Sections 1 to 5 are shared reference that every slice reads. Sections 6, 7 and 8 are self-contained briefs, one per agent, each ending on a completion criterion. Section 9 is the rollout a person runs.

## 1. Outcome

Every client signs in with a phone number and an SMS code. FastAPI decides what each **caller** may do from the **grants** in its own database. The layer is done when this runs on staging:

1. The team admin runs `grant_das.py` for `+40700000001`.
2. That person signs in on the dashboard and sees „Conectat ca …”.
3. With `POST /api/staff` they make `+40700000002` a medic. That person signs in on the Android app and lands on the medic placeholder. `+40700000003`, which holds DAS and medic, gets the role picker.
4. `+40700000009`, which has no grant, sees „Numărul nu este înregistrat. Contactați medicul de familie.” on both clients.

## 2. Decisions

| ID | Decision | Note |
|---|---|---|
| AL1 | In scope: the backend identity core, the `users` and `grants` tables, `GET /api/me`, `POST /api/staff` (API only), `grant_das.py`, `dev_token.py`, dashboard sign-in, Android sign-in | Out of scope: §10 |
| AL2 | A caller's permissions are the **union** of all their grants. The client's role choice picks screens only | G3 |
| AL3 | The role picker appears when the grants span **more than one distinct role**. Several caregiver grants are one role | Rewords 01 §6 "several grants" |
| AL4 | The phone number is the identity key on every request. `firebase_uid` is stored, written when empty, and overwritten with a warning log when it differs | The MVP assumes numbers do not change. The uid is kept for a later second sign-in method or a change-number flow |
| AL5 | Caregivers, and the senior's own app account, are rows in `grants`. `seniors.medic_id` is the only foreign key from `seniors` to `users` | 05 as written. Caregiver to senior is many-to-many with a `relation`; `grants` is that join table |
| AL6 | `grants.senior_id` is a plain nullable `uuid`. Its foreign key arrives with the `seniors` migration | No `seniors` table yet |
| AL7 | At most one `senior` grant per user. When a couple shares one mobile, the second senior has no app role and still receives every call | The rule is recorded now; the seniors migration adds its index |
| AL8 | A senior outside the caller's reach answers 404 `not_found` | Applies to later endpoints; shows a stranger and a revoked caregiver the same thing |
| AL9 | The refusal contract in §3.2 | Extends 04 §0 |
| AL10 | `firebase-admin`, verifying against Google's public keys. No revocation check. The `phone_number` claim is required. Any sign-in provider is accepted when the token carries `phone_number` | Grants give instant revocation |
| AL11 | No service account key anywhere. The API starts the Admin SDK with the project id `sentinela-8f474` and a placeholder credential, because verifying needs nothing more. `dev_token.py` signs a test number in through Firebase's REST API with the public web key | The organisation policy `iam.disableServiceAccountKeyCreation` blocks keys, and a key is a secret that never expires |
| AL12 | `phonenumbers` with region `RO`, stored as E.164. Staff numbers must be mobiles | Staff sign in by SMS |
| AL13 | Every environment uses the real Firebase project and its test numbers. Pytest replaces the token verifier through a dependency override; production code has a single verification path | §5 |
| AL14 | `grant_das.py` grants DAS only. Medics are granted through `POST /api/staff` | G6 |
| AL15 | Each refusal is logged with its reason and the user id, or a masked number (`+40700***009`). Tokens stay out of logs | 06 §4 data minimisation |
| AL16 | Android uses Hilt from this layer on: Dagger ≥ 2.60 and KSP ≥ 2.3.1. Dagger 2.59 added AGP 9 support and 2.60 fixed its slow incremental builds; KSP 2.3.1 added AGP 9's built-in Kotlin. Retrofit stays. Navigation waits for the role screens | Updates the rule in `android/AGENTS.md` |
| AL17 | Delivery: the backend PR first. Then the dashboard and Android in parallel, each in its own worktree and PR | §9 |

**Departures from the system spec**, made consistent by §6.6:

| Where | Change |
|---|---|
| 01 §6 and UC-02 step 5 | The picker chooses among roles (AL3) |
| 04 §1 `/me` | No warning flag and no senior names until the campaign and senior tables exist |
| 05 `users` | No `on_duty` until the on-duty feature |

## 3. Shared contract

### 3.1 Identity on every protected request

1. The client sends `Authorization: Bearer <Firebase identity token>`.
2. FastAPI verifies the token with `firebase-admin`, without `check_revoked`.
3. It takes the `phone_number` claim and passes it through `normalize()` (§3.5).
4. One query loads the user by `phone_e164`, together with their grants.
5. If the token's `uid` differs from `users.firebase_uid`, FastAPI writes the new value. It logs a warning when it replaces a value that was already set.
6. The endpoint checks the caller's roles (AL2).

`/api/health` and the OpenAPI docs at `/api/docs` stay open.

### 3.2 Refusals

The body is FastAPI's own shape: `{"detail": {"reason": "<reason>"}}`. A 401 also carries `WWW-Authenticate: Bearer`. Validation errors keep FastAPI's standard 422 body.

| HTTP | `reason` | When | The client then |
|---|---|---|---|
| 401 | `not_signed_in` | No token, or a malformed, wrongly signed or expired one, or a valid token without a `phone_number` claim | Gets a forced-fresh token and retries once. A second 401 sends it to the sign-in screen |
| 403 | `not_registered` | Valid token, but no user row for the number, or a user with zero grants | Shows „Numărul nu este înregistrat. Contactați medicul de familie.” and signs out of Firebase |
| 403 | `not_allowed` | The caller has grants, but none permits this request | Shows a generic error and stays signed in |
| 404 | `not_found` | The thing does not exist, or a senior outside the caller's reach (AL8) | Shows "not found" |
| 409 | `already_done` | `POST /api/staff` for a grant the number already holds; an incident someone else already took or resolved (the take refusal adds `taken_by_name`) | Shows "already granted", or who has the incident |
| 409 | `wrong_state` | An incident not in the state the command needs: taking a resolved one, resolving an open one (04 §2) | Re-reads the incident |
| 503 | `auth_unavailable` | Google's public keys cannot be fetched | Shows „Autentificarea nu este disponibilă acum. Încercați din nou.” and stays signed in |

### 3.3 `GET /api/me`

Any caller with at least one grant.

```json
{
  "display_name": "Ana Pop",
  "phone_e164": "+40700000003",
  "grants": [
    { "role": "das", "senior_id": null },
    { "role": "medic", "senior_id": null }
  ]
}
```

- **One entry per grant**, sorted `das`, `medic`, `caregiver`, `senior`, then by `created_at`. A caregiver of two seniors has two `caregiver` entries.
- **Zero grants** answer 403 `not_registered` (§3.2).
- **Clients derive the distinct roles** themselves for the picker (AL3).
- **Added with the seniors work:** `senior_form_of_address` and `relation` on each grant, null for das and medic grants.
- **Fields that arrive later, each as an optional addition:** `id`, `practice`, `warning_active` (with campaigns).

### 3.4 `POST /api/staff`

Callable only by a caller who holds a `das` grant; anyone else gets 403 `not_allowed`.

```json
{ "display_name": "Dr. Ion Pop", "phone": "0722 123 456", "role": "medic", "practice": "CMI Dr. Pop" }
```

| Rule | Behaviour |
|---|---|
| `display_name` | 1 to 120 characters after trimming |
| `role` | `medic` or `das`. Anything else is a 422 |
| `practice` | Required, 1 to 200 characters, for `medic`. Ignored for `das` |
| `phone` | Validated inside the request model: it must parse with `normalize()` and be a mobile (§3.5). Otherwise the standard 422 |
| New number | Creates the user and the grant, with `granted_by` set to the caller → **201** |
| Number already known | Adds the grant and keeps the user's existing `display_name`. For `medic`, it sets `practice` → **201** |
| The number already holds that grant | 409 `already_done`. The whole transaction rolls back, so a refused request changes nothing |
| Two grants of the same number at the same moment | Both inserts use `INSERT … ON CONFLICT DO NOTHING`, so the loser gets 409 `already_done` |
| Response | `{ "display_name", "phone_e164", "role", "practice" }` |

### 3.5 Phone numbers

- **`normalize(raw) -> str`** parses with `phonenumbers` using the default region `RO`, requires `is_valid_number`, and returns E.164. Otherwise it raises `ValueError`. Every write and every lookup goes through it, including the number from a token.
- **`is_mobile(e164) -> bool`** is true for the number types `MOBILE` and `FIXED_LINE_OR_MOBILE`.

These results were checked with `phonenumbers` on Python 3.14:

| Input | E.164 | Valid | Type |
|---|---|---|---|
| `0722 123 456` | `+40722123456` | yes | MOBILE |
| `+40700000001` | `+40700000001` | yes | MOBILE |
| `0256 123 456` | `+40256123456` | yes | FIXED_LINE |
| `+16505550101` | `+16505550101` | yes | FIXED_LINE_OR_MOBILE |
| `12345` | n/a | no | n/a |

### 3.6 Permission rules for later endpoints

No endpoint in this layer takes a senior. These rules are fixed now so that the seniors work does not have to reopen them.

- **What a caller sees of one senior** is the union of the grants that cover that senior, using the matrix in 01 §6. For example, the transcript needs medic-of-this-senior or DAS; an event's location needs caregiver or DAS.
- **A medic reaches a senior** when they hold a `medic` grant **and** `seniors.medic_id` is their id. Revoking the grant cuts access even though `medic_id` still points at them.
- **A caregiver or senior reaches a senior** through a grant with that `senior_id`.
- **DAS reaches every senior** whose state is `submitted` or later.
- **Anything else answers 404 `not_found`** (AL8).
- **At most one `senior` grant per user** (AL7).

## 4. Data model

Both tables come from one Alembic migration. The ids are generated by the database with `uuidv7()`, which is built into Postgres 18 both locally and on Railway (04 §0: "the database for rows").

**`users`**

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK, default `uuidv7()` | |
| `phone_e164` | `varchar(16)` unique, not null | Its index serves the lookup on every request |
| `display_name` | `varchar(120)` not null | |
| `firebase_uid` | `varchar(128)` unique, nullable | AL4 |
| `practice` | `varchar(200)` nullable | Medics |
| `created_at` | `timestamptz` not null, default `now()` | |

**`grants`**

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK, default `uuidv7()` | |
| `user_id` | `uuid` not null, FK → `users` `ON DELETE CASCADE` | |
| `role` | `varchar(16)` not null | `CHECK (role IN ('das','medic','caregiver','senior'))` |
| `senior_id` | `uuid` nullable, no FK yet (AL6) | `CHECK ((role IN ('caregiver','senior')) = (senior_id IS NOT NULL))` |
| `relation` | `varchar(60)` nullable | Caregivers |
| `granted_by` | `uuid` nullable, FK → `users` | Empty means the setup script |
| `created_at` | `timestamptz` not null, default `now()` | |

- **Uniqueness:** `UNIQUE NULLS NOT DISTINCT (user_id, role, senior_id)`. The `NULLS NOT DISTINCT` part is what makes a `das` or `medic` grant, whose `senior_id` is NULL, unique per user. The index starts with `user_id`, so it also serves the grant lookup on every request; no second index is needed.
- **Revoking a grant deletes its row** (05 §5).
- **The Python side:** `Role` is a `StrEnum` mirroring the CHECK.

## 5. Test numbers

These are configured in the Firebase console under Authentication → Sign-in method → Phone → *Phone numbers for testing*. Firebase sends no SMS for them. Any device or browser signs in as any of them by typing the number and its code. They are demo values, not secrets.

| Number | Code | Granted as |
|---|---|---|
| `+40700000001` | `111111` | DAS (`grant_das.py`) |
| `+40700000002` | `222222` | medic (`POST /api/staff`) |
| `+40700000003` | `333333` | DAS (`grant_das.py`) and medic (`POST /api/staff`): exercises the role picker |
| `+40700000009` | `999999` | nothing: exercises `not_registered` |

Grants live in each environment's database (ADR-001), so each environment needs its own grants (§9).

Test numbers suit staff and caregivers. A **senior's** number must be a real team phone, because Twilio really dials it. That warning is for the seniors work.

## 6. Slice 1: Backend

**Branch:** `auth-layer`. **Read first:** [backend/AGENTS.md](../../backend/AGENTS.md), then §1 to §5 of this file.

### 6.1 Files

| File | Holds |
|---|---|
| `app/phones.py` | `normalize()`, `is_mobile()` (§3.5) |
| `app/models.py` | `Role`, `User`, `Grant` (§4) |
| `app/db.py` | adds an `async_sessionmaker` and a `get_session` dependency next to the existing `engine` |
| `app/auth.py` | Firebase initialisation; `verify_token`, a plain `def` dependency that returns the claims; `Caller` (the user, the grants, a `roles` set); the `current_caller` and `require_roles(*roles)` dependencies; the refusals of §3.2; the logging of AL15 |
| `app/staff.py` | `grant_staff(session, display_name, phone_e164, role, practice, granted_by) -> created: bool`, shared by the route and the script |
| `app/main.py` | `GET /api/me` and `POST /api/staff` on the `api` router; an `HTTPBearer(auto_error=False)` scheme so Swagger shows *Authorize* |
| `scripts/grant_das.py` | `python scripts/grant_das.py "<name>" <phone>`: validates like §3.4, grants `das` with no `granted_by`, prints `granted` or `already granted`, exits 0; an invalid number exits 2 |
| `scripts/dev_token.py` | `python scripts/dev_token.py <phone> <code>`, for a test number of §5: calls `https://identitytoolkit.googleapis.com/v1/accounts:sendVerificationCode?key=<web API key>` with `{"phoneNumber": …, "recaptchaToken": "dev"}`, then `accounts:signInWithPhoneNumber` with the `sessionInfo` and the code, using stdlib `urllib`, and prints the `idToken`. The web API key is the public `VITE_FIREBASE_API_KEY` from `.railway/railway.ts` |
| `alembic/versions/<rev>_users_and_grants.py` | the migration (§4) |
| `tests/conftest.py` and `tests/test_*.py` | §6.4 |

### 6.2 Facts that are hard to find by looking

- **`verify_id_token` loads a credential it never uses.** With only a project id it raises `DefaultCredentialsError`, because the SDK's auth client calls `get_credential()` when it is built. A `credentials.Base` subclass that returns `google.auth.credentials.AnonymousCredentials()` satisfies it; verification itself needs only the project id and Google's public keys. Probed with firebase-admin 7.7.0 on Python 3.14.
- **Test numbers sign in over REST.** For a test number, `accounts:sendVerificationCode` accepts any `recaptchaToken` string, so `dev_token.py` needs no service account.
- **Exception mapping.** `CertificateFetchError` maps to 503 `auth_unavailable`. Every other error from `verify_id_token`, and a `ValueError` from a malformed token, maps to 401 `not_signed_in`. The returned claims carry the Firebase user id as `uid`.
- **firebase-admin is synchronous.** A plain `def` dependency runs in FastAPI's thread pool, which keeps the live-call WebSockets responsive (01 §8). Google's public keys are cached by the SDK.
- **Alembic only sees imported models.** `alembic/env.py` imports `app.db.Base` alone. Add `import app.models  # noqa: F401` there, so autogenerate sees the tables.
- **Review the autogenerated migration against §4.** Confirm both CHECK constraints, `postgresql_nulls_not_distinct=True` on the unique constraint (declared in the model as `UniqueConstraint(..., postgresql_nulls_not_distinct=True)`), and the `uuidv7()` server defaults are in the file.
- **CORS needs no change.** Starlette answers a preflight under `allow_headers=["*"]` by mirroring the requested headers, `Authorization` included.
- **The database URL is fixed at import.** `app/db.py` builds the engine from settings when it is imported, and pydantic-settings prefers environment variables to `backend/.env`. `tests/conftest.py` sets `DATABASE_URL` to `postgresql://sentinela:sentinela@localhost:5432/sentinela_test` **before** importing anything from `app`.
- **One event loop per test session.** asyncpg's pooled connections belong to the loop that opened them, and the engine is module-level. Run every test and fixture on one session-scoped loop: pytest-asyncio with `asyncio_default_fixture_loop_scope = "session"` and `asyncio_default_test_loop_scope = "session"` in `pyproject.toml`, and httpx's `AsyncClient(transport=ASGITransport(app))`.
- **`alembic/env.py` calls `asyncio.run`.** Run migrations in tests from a synchronous session fixture, for example `subprocess.run(["alembic", "upgrade", "head"], check=True)`, before any test's loop starts. `env.py` accepts `localhost` as a local database.
- **The image ships `scripts/`.** The Dockerfile copies the whole folder, so `grant_das.py` runs inside the container (`railway ssh`, or `docker compose exec api`).

### 6.3 Steps

Each step is done when its criterion holds.

1. **Dependencies.** `uv add firebase-admin phonenumbers`, and `uv add --dev pytest-asyncio httpx`. *Done:* `uv sync --locked` succeeds and `uv.lock` is committed.
2. **`app/phones.py`.** *Done:* a test asserts every row of the table in §3.5.
3. **Models and migration.** Write the models and add the import to `alembic/env.py`. Then generate the migration inside Compose, as `backend/AGENTS.md` says, and review it against §4. *Done:* `alembic upgrade head` on a fresh `sentinela_test` creates exactly `users` and `grants` with every constraint in §4, and `alembic downgrade base` removes them.
4. **Keyless startup.** *Done:* a test in `tests/test_verify.py` shows that, with no credential on the machine, `verify_token` answers a malformed token with 401 `not_signed_in`.
5. **`app/auth.py`.** *Done:* the refusal matrix in §6.4 passes.
6. **`app/staff.py` and both routes.** *Done:* the `/me` and `/staff` tests in §6.4 pass, and `/api/docs` shows *Authorize*.
7. **Scripts.** *Done:* a test runs `grant_das.py`'s entry function twice against the test database and sees `granted`, then `already granted`. `dev_token.py` is checked in step 10.
8. **CI.** Add a `postgres:18` service to `.github/workflows/backend.yml` with user and password `sentinela` and database `sentinela_test`, and set `DATABASE_URL` for the test step. *Done:* the workflow passes on the branch.
9. **Docs.** Make the changes in §6.6. *Done:* every row of §6.6 is changed.
10. **Real-token check.** Start Compose, grant `+40700000001` with `grant_das.py`, run `dev_token.py +40700000001 111111`, then `curl -H "Authorization: Bearer <token>" localhost:8000/api/me`. *Done:* the response is 200 with a `das` grant. If the response is 401 because the token has no `phone_number` claim, stop and report it with the token's decoded claims, and leave the verifier unchanged.

### 6.4 Test checklist

The verifier is replaced with `app.dependency_overrides[verify_token]`. `Bearer +40…` becomes `{"uid": "test-<number>", "phone_number": "<number>"}`. `Bearer invalid` raises the 401. `Bearer no-phone` returns claims without `phone_number`. Between tests, run `TRUNCATE grants, users CASCADE`.

**Refusal matrix**, on both `GET /api/me` and `POST /api/staff`:

| Case | Expected |
|---|---|
| No header | 401 `not_signed_in` |
| `invalid` | 401 `not_signed_in` |
| `no-phone` | 401 `not_signed_in` |
| An unknown number | 403 `not_registered` |
| A user with zero grants | 403 `not_registered` |
| A medic calling `/staff` | 403 `not_allowed` |
| A DAS calling `/staff` | 201 |

Every 401 carries `WWW-Authenticate: Bearer`.

**`/me`**
- A DAS-and-medic user gets both grants in the order of §3.3.
- A user with two caregiver grants (inserted directly) gets two entries.

**`firebase_uid` (AL4)**
- Written on the first request.
- Unchanged and not rewritten on the second.
- Overwritten when the claims carry a new `uid`, with a warning logged.

**`/staff`**
- A new number gets 201, and the database has the user and a grant with `granted_by` set.
- A known number keeps its `display_name`, and gets `practice` set when the grant is `medic`.
- A repeated grant gets 409 `already_done`, and nothing in the database changed.
- A medic without `practice` gets 422; a landline gets 422; an unparseable number gets 422; the role `caregiver` gets 422.
- Two concurrent grants of the same number and role produce exactly one 201 and one 409.

**Database**
- A duplicate `das` grant for one user is refused.
- A `caregiver` grant without `senior_id` is refused.
- A `das` grant with a `senior_id` is refused.

**Logging**
- A `not_registered` refusal logs the masked number and never the token.

### 6.5 Completion criterion

Slice 1 is done when all of these hold:
- Every item in §6.4 passes in `uv run pytest`.
- `uv run ruff check .` and `uv run ruff format --check .` pass.
- `backend.yml` is green on the branch.
- Every row of §6.6 is changed.
- Step 10 is reported with its result.

Open the PR only when the person who dispatched you asks for it.

### 6.6 Spec and config changes in this PR

The contract and the docs move together (root `AGENTS.md`).

| File | Change |
|---|---|
| `docs/specs/sentinela/04-interfaces.md` §0 | `Authorization: Bearer`; the reasons and the body shape of §3.2 |
| same file, §1 | The `/me` row matches §3.3, and says the warning flag and senior names arrive with their tables |
| same file, §2 | The "Grant staff" row matches §3.4 |
| `docs/specs/sentinela/01-architecture.md` §6 | AL2, AL3, AL4, AL7, AL8, and the medic rule in §3.6 |
| `docs/specs/sentinela/02-use-cases.md` UC-02 step 5 | "Several roles" instead of "several grants" |
| `docs/specs/sentinela/05-data-model.md` §3 and §4 | At most one senior grant per user (enforced with the seniors migration); the `firebase_uid` overwrite rule |
| `docs/specs/sentinela/06-operations.md` §4 | The logging rule (AL15) |
| `backend/AGENTS.md` | The layout gains the new modules and `scripts/` |
| `backend/README.md` | The test numbers (§5); how to grant locally; how to use `dev_token.py` with Swagger's *Authorize* and with curl |

## 7. Slice 2: Dashboard

**Branch:** `auth-dashboard`, in its own worktree, cut from `main` after slice 1 has merged. **Read first:** [dashboard/AGENTS.md](../../dashboard/AGENTS.md), then §1 to §5 of this file.

**Local setup.** Grant the test numbers locally:
- DAS: `docker compose exec api python scripts/grant_das.py "DAS Test" +40700000001`, and the same for `…003`.
- Medic: make `…002` and `…003` medics through `POST /api/staff`, with a token from `dev_token.py +40700000001 111111` (`backend/README.md`).

### 7.1 Behaviour

| File | Holds |
|---|---|
| `src/firebase.ts` | `initializeApp` from the existing `VITE_FIREBASE_*` variables; exports `auth` from `firebase/auth`. Default persistence, so a desk session survives reloads |
| `src/api.ts` | `apiFetch(path, init)`: adds `Authorization: Bearer ${await auth.currentUser.getIdToken()}`. On a 401 it retries once with `getIdToken(true)`; on a second 401 it signs out. `getMe()` |
| `src/SignIn.tsx` | Phone step, then code step. An invisible `RecaptchaVerifier` and `signInWithPhoneNumber` |
| `src/App.tsx` | Replaces the health-check skeleton. Driven by `onAuthStateChanged` and `getMe()` |

**Turning what the person types into E.164 before sending:**
1. Strip spaces, dashes, dots and brackets.
2. Change a leading `00` to `+`.
3. Change a leading `0` to `+40`.
4. Prefix a bare `7…` with `+40`.
5. Keep a leading `+` as it is.

The server normalizes again.

**What `App` shows, by state:**

| State | Shows |
|---|---|
| Signed out | `SignIn` |
| Signed in, `/me` returns 200 with a `das` grant | „Conectat ca {display_name}” and an *Ieșire* button. Later features replace this view |
| `/me` returns 200 without a `das` grant | „Acest număr nu are acces la dispecerat.”, then sign out |
| `/me` returns 403 `not_registered` | „Numărul nu este înregistrat. Contactați medicul de familie.”, then sign out |
| `/me` returns 503 | „Autentificarea nu este disponibilă acum. Încercați din nou.”, still signed in |

**Romanian copy:**

| Element | Text |
|---|---|
| Title | „Intrați în cont” |
| Phone label | „Număr de telefon” |
| Phone button | „Trimite codul” |
| Code label | „Codul primit prin SMS” |
| Code button | „Confirmă” |
| Wrong code (`auth/invalid-verification-code`) | „Cod greșit.” |
| Bad number (`auth/invalid-phone-number`) | „Număr de telefon invalid.” |
| Too many attempts (`auth/too-many-requests`) | „Prea multe încercări. Încercați mai târziu.” |

**React StrictMode mounts effects twice.** Create the `RecaptchaVerifier` lazily when *Trimite codul* is pressed, keep it in a ref, and call `.clear()` on failure and on unmount. A verifier created in an effect renders twice into the same element and throws. The Firebase v10+ constructor takes `auth` first: `new RecaptchaVerifier(auth, element, { size: "invisible" })`.

Add the `firebase` npm package through `npm install firebase`.

### 7.2 Completion criterion

Slice 2 is done when all of these hold:
- `npx vp check` and `npm run build` pass.
- On `localhost:5173` against Compose:
  - `+40700000001` signs in and sees „Conectat ca …”.
  - *Ieșire* returns to `SignIn`.
  - `+40700000009` sees the not-registered text.
  - `+40700000002`, once granted medic only, sees „Acest număr nu are acces la dispecerat.”
  - Reloading a signed-in page stays signed in.

Report each of these observations. Open the PR only when the person who dispatched you asks for it.

## 8. Slice 3: Android

**Branch:** `auth-android`, in its own worktree, cut from `main` after slice 1 has merged. **Read first:** [android/AGENTS.md](../../android/AGENTS.md), [android/app/AGENTS.md](../../android/app/AGENTS.md), then §1 to §5 of this file.

**Preconditions:**
- `android/app/google-services.json` exists. A person registers `bia.sentinela` in Firebase and downloads it. The `google-services` plugin fails the build without it, and a red Android build also holds back API deploys (root `AGENTS.md`). If the file is missing, stop and report.
- The shared keystore is in `local.properties` (android/AGENTS.md).
- Debug builds talk to staging unless `sentinela.apiUrl` is set, so the test numbers need grants on staging (§9) or on the local Compose stack.

### 8.1 Build

Everything goes through `gradle/libs.versions.toml`, on `:app` only. `:wear` stays as it is.

| Addition | Note |
|---|---|
| The `com.google.gms.google-services` plugin | `google-services.json` is committed (ADR-001: identifiers, not secrets) |
| The Firebase BoM and `firebase-auth` | |
| `kotlinx-coroutines-play-services` | `await()` on Firebase `Task`s |
| Hilt: the `com.google.dagger.hilt.android` plugin and `hilt-android` ≥ 2.60, with `hilt-compiler` through KSP | AL16 |
| KSP: `com.google.devtools.ksp` ≥ 2.3.1 | Its versions no longer follow Kotlin's |
| `androidx.hilt:hilt-lifecycle-viewmodel-compose` | For `hiltViewModel()` without Navigation |

If Hilt or KSP cannot build under AGP 9.4.1 even with matching versions, stop and report the build error.

### 8.2 Structure

- **`SentinelaApp`**, annotated `@HiltAndroidApp` and named in the manifest. `MainActivity` becomes `@AndroidEntryPoint`.
- **`FirebaseModule`** provides `FirebaseAuth`. Debug builds (`BuildConfig.DEBUG`) set `firebaseAuthSettings.setAppVerificationDisabledForTesting(true)`. That affects only test numbers, and it lets emulators sign in before the SHA fingerprints are registered.
- **`NetworkModule`** provides:
  - OkHttp with an interceptor that adds `Authorization: Bearer` from `Tasks.await(user.getIdToken(false))`, which runs on OkHttp's thread.
  - An `Authenticator` that answers a 401 by retrying once with `getIdToken(true)`; it gives up on a request that was already retried.
  - Retrofit, at `BuildConfig.API_URL + "/api/"`, with the existing lenient `Json`.
  - `SentinelaApi`, which gains `@GET("me") suspend fun me(): Me`.

  The `Api` object is removed.
- **`Me` decodes roles as strings.** Clients drop a role this build does not know (android/app/AGENTS.md: decode leniently).
- **One `@HiltViewModel` exposes a sealed screen state:** `Phone`, `Code`, `Loading`, `NotRegistered`, `Unavailable`, `PickRole(roles)`, `Home(role, displayName)`.
- **The Activity starts phone verification, not the ViewModel.** `PhoneAuthOptions` needs an `Activity` for the reCAPTCHA fallback, and the ViewModel never holds one. The Activity builds the options, passes the callbacks' results into the ViewModel, and uses a 60-second timeout:
  - `onVerificationCompleted` (automatic SMS reading) signs in straight away.
  - `onCodeSent` keeps the verification id and the resend token.
  - *Retrimite codul* becomes available after 30 seconds.
- **The role choice is saved in `SharedPreferences`.** A saved role that is no longer among the grants is dropped. With one distinct role, `Home` opens directly.
- **The menu** in `Home` holds *Ieșire*, and *Schimbă rolul* when there are several roles.
- **The skeleton health screen goes.**

**What the app does with each answer from `/me`**, as a pure function in `bia.sentinela.auth`, unit-tested on the JVM:

| `/me` answer | Next screen |
|---|---|
| 200 with one distinct role | `Home(role)` |
| 200 with several roles and a valid saved role | `Home(saved)` |
| 200 with several roles and no valid saved role | `PickRole` |
| 403 `not_registered` | `NotRegistered`, then sign out |
| 503 | `Unavailable` |

**Romanian strings**, in `strings.xml`:

| Key | Text |
|---|---|
| Sign-in title | „Intrați în cont” |
| Phone field | „Număr de telefon” |
| Send code | „Trimite codul” |
| Code field | „Codul primit prin SMS” |
| Confirm | „Confirmă” |
| Resend | „Retrimite codul” |
| Wrong code | „Cod greșit.” |
| Not registered | „Numărul nu este înregistrat. Contactați medicul de familie.” |
| Unavailable | „Autentificarea nu este disponibilă acum. Încercați din nou.” |
| Picker title | „Alegeți rolul” |
| Role labels | `das` „Dispecerat DAS”, `medic` „Medic”, `caregiver` „Aparținător”, `senior` „Senior” |
| Home | „Conectat ca %1$s · %2$s” |
| Menu | „Schimbă rolul”, „Ieșire” |

The phone field applies the same E.164 conversion as the dashboard (§7.1).

**`android/AGENTS.md`'s rule changes:** Hilt is the DI framework; Navigation and Room still arrive with the first feature that needs them.

### 8.3 Completion criterion

Slice 3 is done when all of these hold:
- CI's command `./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug` passes, including the screen-decision test.
- A release build installs and launches on an emulator, which checks R8 and Hilt.
- On an emulator against an API where the test numbers are granted:
  - `+40700000001` reaches the DAS home.
  - `+40700000003` sees the picker; the chosen role survives an app restart; *Schimbă rolul* returns to the picker.
  - `+40700000009` sees the not-registered text and is signed out.
  - *Ieșire* returns to the phone screen.

Report each of these observations, with screenshots from `android screen capture`. Open the PR only when the person who dispatched you asks for it.

## 9. Rollout

Steps marked *person* are done by a team member; agents leave cloud environments alone (root `AGENTS.md`).

1. *Person.* Register the Android app `bia.sentinela` in Firebase and download `google-services.json` for slice 3. Registering the SHA-1 and SHA-256 of the shared keystore (ADR-001 action item 3) is needed for real numbers on real devices, but not for test numbers on debug builds.
2. Slice 1 merges to `main`. Staging migrates in its pre-deploy step.
3. *Person.* Inside staging's `api` container (`railway ssh`), run `python scripts/grant_das.py "DAS Test" +40700000001`, and the same for `+40700000003`.
4. `dev_token.py +40700000001 111111` gives a token for staging's `POST /api/staff`. Use it to grant `+40700000002` and `+40700000003` as medics.
5. Slices 2 and 3 run in parallel, each in its own worktree and PR.
6. *Person.* Before promoting `main` to `release`, repeat step 3 for production.

## 10. Later, outside this layer

| Item | Belongs to |
|---|---|
| Push tokens: `PUT/DELETE /me/push-tokens`, the `push_tokens` table, the FCM dependency on Android | The push work (G4) |
| `GET /staff`, on-duty (`users.on_duty`), the dashboard's „Personal” screen | The staff feature (UC-14 UI, P10) |
| Twilio request signatures on callbacks and the WebSocket | The Twilio work (spike S1, `PUBLIC_BASE_URL`) |
| The `seniors` table; `seniors.medic_id`; the FK on `grants.senior_id`; the partial unique index for AL7; the senior-scoped helper for §3.6; `/me`'s senior names | The seniors work (UC-01) |
| `warning_active` on `/me` | The campaign work (UC-05) |
| App Check, rate limits | Before a pilot |

## 11. Facts still to confirm

| Fact | Confirmed by |
|---|---|
| A custom-token sign-in's identity token carries `phone_number` | §6.3 step 10 |
| The four test numbers and codes in §5 match the console | The person, when configuring |
