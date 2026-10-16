# CRUD completion: design

**Date:** 2026-10-16
**Status:** Settled in two grilling rounds (2026-10-15 and 2026-10-16); awaiting review of this document
**Classification:** Architectural (changes the `04-interfaces.md` contract)
**Scope:** `backend/app/`, `backend/tests/`, the specs under `docs/specs/`, one change in `android/app/`
**Branches:** `crud-backend` (this spec, backend, spec docs) and `android-phone-taken` (Android), both from `main`

---

## 1. Goal

Finish the create, read, update and delete endpoints for the entities the system already has, so the next client screens aren't blocked. The milestone is the end-to-end demo with fictitious people (`05 §5`). Shapes stay safe for a pilot: nothing with history is ever hard-deleted.

Success means:

- Every endpoint in §4 exists, behaves as written there, and has tests.
- `04-interfaces.md` and the other spec files in §7 match the code.
- Android's „Pacient nou” form explains a `phone_taken` refusal.
- No migration. `uv run pytest`, `ruff`, `lint-imports` and `alembic check` all pass.

## 2. Non-goals

- **Writes that start the call pipeline:** `POST /campaigns`, `GET /campaigns` (built together with it later), `POST /seniors/{id}/welcome-call`, and device intake (`/me/events`, `/me/check-ins`, `/me/room-readings`).
- **Client screens for the new endpoints.** The dashboard and Android pick them up when their screens are built. The one exception is §6.
- **Editing your own profile** (`PATCH /profile`). Every name a person could get wrong is already fixable by someone else (§4.1, §4.3).
- **Reassigning a medic, returning from `withdrawn`, pagination.** See §9.

## 3. Decisions

From the grilling rounds. Q numbers refer to those rounds.

| # | Decision |
|---|---|
| Q3 | Hard `DELETE` only for rows with no history: grants, push tokens, seniors in `draft`. Anything else changes state instead |
| Q4 | New edit endpoints are `PATCH`: a missing field means "unchanged". `PUT /seniors/{id}` stays a full replace |
| Q5, Q11 | SE9 and SE10 of [seniors-and-enrollment.md](../../specs/seniors-and-enrollment.md) now win over `04 §2`. The registering medic **and** DAS (within reach) may edit a registration and its caregivers in **any** state. A mobile number already used by another senior is refused with `phone_taken`. Creating, submitting, deleting and signing stay the medic's; accepting stays DAS's |
| Q6 | Removing the last `das` grant in the system is refused |
| Q7 | A medic who loses the role keeps their seniors' `medic_id`. Granting `medic` again restores everything |
| Q8 | A staff member's phone number can't be edited. It is how they sign in |
| Q10 | A senior can be deleted only as a `draft`, only by the registering medic, and only if no call references it |
| Q12 | Submitting still needs at least one caregiver, and past `draft` the last one can't be removed (`04 §2`, not SE4) |
| Q13 | Editing a caregiver can change the relation and the name. The name is on the shared user row, so it changes everywhere |
| Q15 | Withdrawing consent moves the senior to a new enrollment state, `withdrawn`. The medic or DAS may record it |
| Q18 | Backend and specs only, plus the Android `phone_taken` message (§6) |
| Q19 | Push tokens live under `/profile/push-tokens/{token}`, following today's `/me` → `/profile` rename |
| Q22 | A caregiver edit can't rename someone who holds `das` or `medic`. Staff names change only through `PATCH /staff/{user_id}`, so a medic can't rename a dispatcher on every incident they handled |

## 4. The endpoints

All paths are under `/api`. Refusals use the existing `refuse()` shape, `{"detail": {"reason": …}}` (`04 §0`). "Editor" below means **the registering medic, or a DAS employee who reaches the senior** (§5.1).

### 4.1 Staff (`app/staff/`)

| Request | Who | Body | Effect | Answers | Refused |
|---|---|---|---|---|---|
| `DELETE /staff/{user_id}/roles/{role}` | DAS | none; `role` is `das` or `medic` | Deletes that grant. Removing `das` also sets `on_duty = false`. Removing yourself is allowed. An incident the person holds stays theirs; any DAS can still resolve it | 204, also when there was no such grant or user | It would leave no `das` grant in the system: 409 `wrong_state`. Another `role`: FastAPI's 422 |
| `PATCH /staff/{user_id}` | DAS | `display_name?`, `practice?` (same limits as `POST /staff`) | Updates the user row. No phone field | One row of `GET /staff` | The user holds neither `das` nor `medic`: 404 `not_found`. `practice` for someone without `medic`: 422 `not_medic` |
| `PUT /staff/on-duty` | DAS | `user_id` | Everyone else off duty, this person on | 204, also on a repeat | `user_id` has no `das` grant: 403 `not_allowed` |
| `DELETE /staff/on-duty` | DAS | none | Nobody on duty. The hand-over already handles that (`04 §4.2`) | 204 | Never |

### 4.2 Seniors (`app/seniors/`)

| Request | Who | Change from today | Refused |
|---|---|---|---|
| `POST /seniors` | Medic | Also refuses a reused mobile | A mobile that already holds a senior grant for another senior: 409 `phone_taken` |
| `PUT /seniors/{id}` | Editor (was: registering medic) | Allowed in **every** state (was: `draft` and `submitted` only). Changing an active senior's number just moves the senior grant; no new welcome call | Past `draft`, a body without street or street number: 422 `incomplete` with `missing` (unchanged). A **changed** number that is another senior's mobile: 409 `phone_taken` (§5.2) |
| `POST /seniors/{id}/caregivers` | Editor (was: registering medic) | n/a | Unchanged |
| `DELETE /seniors/{id}/caregivers/{user_id}` | Editor (was: registering medic) | n/a | Unchanged: past `draft`, the last caregiver stays (422 `incomplete`, `missing: ["caregiver"]`) |

New:

| Request | Who | Body | Effect | Answers | Refused |
|---|---|---|---|---|---|
| `PATCH /seniors/{id}/caregivers/{user_id}` | Editor | `relation?`, `display_name?` (same limits as `CaregiverForm`) | Updates the grant's `relation` and the user row's `display_name` | `CaregiverView` | `user_id` is not a caregiver of this senior: 404 `not_found`. A `display_name` for a person who holds `das` or `medic`: 403 `not_allowed`, nothing changed (Q22) |
| `DELETE /seniors/{id}` | Registering medic | none | Deletes the senior's consents, then the senior. Grants go with it (`ON DELETE CASCADE`) | 204. A repeat is 404 `not_found` (the row is gone) | Not `draft`: 409 `wrong_state`. Any other row still references the senior, such as a call from `place_call.py`: 409 `wrong_state`, and nothing is deleted |
| `POST /seniors/{id}/consent-withdrawn` | Editor | none | `active` → `withdrawn`, and a consent row: decision `withdrawn`, method `medic` if the caller is the registering medic, otherwise `das`; `text_version` copied from the senior's latest consent row, or `"none"` if there is none; `recorded_by` the caller. One transaction | One row of `GET /seniors` (`SeniorSummary`), like submit | Already `withdrawn`: 409 `already_done`. Any other state: 409 `wrong_state` |
| `POST /seniors/{id}/signature` | Registering medic | `text_version` (1–40 chars), `strokes`: a list of strokes, each a list of `[x, y]` points with `0 ≤ x, y ≤ 1`. At least one stroke; each stroke at least one point; at most 5,000 points in total | Adds a consent row: decision `given`, method `signature`, the strokes in `signature_strokes`, `recorded_by` the caller. The latest signature counts | 204 | State not `draft`, `submitted` or `accepted`: 409 `wrong_state`. A bad body: FastAPI's 422 |

`POST …/signature` is not repeat-safe: two posts add two rows. That's harmless, since the latest one counts. Like SE14, it's an exception to `04 §0`.

### 4.3 Calls (new package `app/calls/`)

| Request | Who | Answers | Refused |
|---|---|---|---|
| `GET /seniors/{id}/calls` | Anyone who reaches the senior (`reach_senior`) | A list of `CallSummary`, newest first (`created_at` desc, then `id`), queued calls included, `trigger = test` calls left out (`05 §1`). No pagination. `CallSummary`: `id`, `trigger`, `state`, `due_at`, `started_at`, `ended_at`, `final_severity`, `final_certainty`, `reason`, `summary` | Out of reach: 404 `not_found` |
| `GET /calls/{id}/transcript` | The senior's registering medic, or DAS for a senior past `draft` | `TranscriptDetail`: the incident page's `CallDetail` (turns and reports) plus `answers`, a list of `AnswerView` (`field`, `value`, `clear`, `quote`, `at`), ordered by `at`. Test calls are served too | No such call, or the caller reaches its senior only as caregiver or senior: 404 `not_found` |

The transcript's access check is `or_(reach(caller, Role.medic), reach(caller, Role.das))` on the call's senior. Both role-narrowed reaches already exist in `seniors/service.py`.

### 4.4 Push tokens (`app/auth/`)

| Request | Who | Effect | Answers |
|---|---|---|---|
| `PUT /profile/push-tokens/{token}` | Any signed-in number with a grant | Upsert on the unique `token`: insert it for the caller, or move an existing row to the caller (a shared tablet) and touch `updated_at` | 204 |
| `DELETE /profile/push-tokens/{token}` | Same | Deletes the row only if it is the caller's | 204, always |

A token longer than 512 characters (the column) is FastAPI's 422.

### 4.5 New enum members and refusal reasons

- `EnrollmentState.withdrawn`, `ConsentMethod.das`. Enums are stored as `VARCHAR(32)` with no `CHECK` (`StoredEnum`, `app/core/db.py`), so neither needs a migration. `alembic check` must stay clean.
- New reasons: `phone_taken` (409) and `not_medic` (422). Both go into `04 §0`.

## 5. How it fits the code

### 5.1 Who may act on a senior

Today `own_senior()` serves every command: the senior locked, and the caller must be the registering medic. Add one sibling in `seniors/service.py`:

- `editable_senior(session, caller, senior_id)`: `reach_senior(…, lock=True)`. It is allowed if the caller holds `medic` and is the registering medic, or holds `das`. Otherwise 403 `not_allowed`. DAS doesn't reach drafts, so DAS on a draft is 404, as today.

It serves `PUT /seniors/{id}`, the three caregiver endpoints and `consent-withdrawn`. Their routes change `require_roles(Role.medic)` to `require_roles(Role.medic, Role.das)`. `own_senior()` keeps serving submit, delete and signature. `edit()` loses its state check, and keeps the `incomplete` check for any state past `draft` (today it only checks in `submitted`).

### 5.2 `phone_taken`

`sync_senior_grant()` keeps its `ON CONFLICT DO NOTHING` insert and now returns whether the senior holds its number's grant afterwards: `True` for a landline, or when the grant is this senior's; `False` when the number belongs to another senior. The `uq_grants_one_senior_per_user` index stays the real guard, so two saves at once can't both win. SE12 (a number that is both the senior and one of their caregivers) is unaffected.

The refusal is the caller's decision. `register()` refuses with 409 `phone_taken` on `False`. `edit()` refuses on `False` **only when the body's phone differs from the stored one**, so a senior left over from the old shared-mobile rule (AL7) can still have their street fixed. Roll back before refusing. `scripts/seed.py` calls `sync_senior_grant()` too and ignores the result, as today. The existing `test_a_couple_sharing_a_mobile` now expects the second registration to be refused with `phone_taken`.

### 5.3 Staff writes that can race

The "last `das`" check (count, then delete) and the on-duty switch (clear everyone, then set one) are each two statements. The partial unique index on `on_duty` turns a race into an `IntegrityError`, which would surface as a 500. So `DELETE /staff/{…}/roles/das`, `PUT /staff/on-duty` and `DELETE /staff/on-duty` each start their transaction with `pg_advisory_xact_lock` on one fixed key. Granting `das` doesn't need the lock: racing a revoke can only make the revoke refuse.

`GET /staff`'s query moves from `staff/router.py` into `staff/service.py`, so `PATCH /staff/{user_id}` can return one row built the same way.

### 5.4 Deleting a draft

Delete `consents` for the senior, then the senior, in one transaction. A foreign-key `IntegrityError` (a call, or anything else that references the senior) rolls everything back and becomes 409 `wrong_state`. That's why `seniors` doesn't need to import `voice`: importing it would be a package cycle, because `voice` already imports `seniors`.

### 5.5 Package placement

`app/calls/` is a new feature package: an empty `__init__.py`, `router.py`, `service.py` and `schemas.py`, mounted in `main.py`. It imports `seniors` (reach), `voice` (the ORM classes) and `incidents` (`CallDetail`, `TurnView`, `ReportView`, `call_detail`). Nothing imports `calls`, so the package graph stays acyclic. `uv run lint-imports` must pass without changing a contract.

Names follow `backend/AGENTS.md`: request bodies end in `Form` (`StaffEditForm`, `OnDutyForm`, `CaregiverEditForm`, `SignatureForm`), responses in `View`, `Summary` or `Detail`.

## 6. Android (`android-phone-taken`)

`enroll/Refusal.kt` maps every unknown 409 to `WrongState`, which re-reads the senior. That's safe, but the medic never learns why the save failed. Add `Refusal.PhoneTaken`, mapped from `409` with reason `phone_taken`, ahead of the catch-all. Step 1 of the form shows it on the phone field, with a new string resource: „Acest număr este deja al altui senior.” (the text in seniors-and-enrollment §3). Add a JVM unit test next to the existing `Refusal` tests. Nothing else changes in Android.

## 7. Spec documents to update (on `crud-backend`)

| File | Change |
|---|---|
| `docs/specs/echocare/04-interfaces.md` | §0: `phone_taken`, `not_medic`. §2: rows for every endpoint in §4, with the "who" changes from §4.2, and `/profile/push-tokens` instead of `/me/push-tokens`. §1: the calls and transcript rows match §4.3 |
| `docs/specs/echocare/05-data-model.md` | `enrollment_state` gains `withdrawn`. `consent.method` gains `das`, with `recorded_by` "for method signature, medic or das". The one-senior-grant rule reads as SE10 |
| `docs/specs/seniors-and-enrollment.md` | The note under the title: SE9 and SE10 are in force again (this spec); SE4 and SE13 stay replaced by `04 §2` |
| `docs/specs/auth-layer.md` | AL7 and §3.6 match SE10 and SE9 |
| `docs/specs/echocare/01-architecture.md` §6 | DAS may edit a registration and add, edit or remove caregivers |
| `docs/specs/echocare/02-use-cases.md` | Wherever enrollment states or the withdrawal are described: the `withdrawn` state |

Search the other spec files for lists of enrollment states and add `withdrawn` where one appears.

## 8. Tests and rollout

**Tests.** Follow the existing files: `tests/staff/test_staff.py`, `tests/seniors/test_seniors.py`, `tests/auth/test_profile.py`, and a new `tests/calls/`. As `06 §5` asks, call every new endpoint as each role, as a number with no grant, and signed out. Each refusal in §4 gets a test. So do the last-`das` guard, `phone_taken` on both create and edit, a draft with a call, and DAS editing an `active` senior. The concurrency paths in §5.3 need no test.

**Old clients.** Opening `PUT` and the caregiver endpoints to more states and to DAS only removes refusals. The new `phone_taken` reaches today's Android build as an unknown 409, which re-reads the senior. Both apps already show an enrollment state they don't know: Android with no label, the dashboard as the raw word.

**Rollout.** Two PRs into `main`, in either order: `crud-backend`, then `android-phone-taken`. No migration and no new setting. Merging `crud-backend` redeploys staging's `api`.

## 9. Later

- `GET /campaigns`, together with `POST /campaigns`.
- Reassigning a medic, so a revoked medic's drafts don't become unreachable (Q7).
- A way back from `withdrawn` (a new welcome call, which is pipeline work).
- Client screens: removing staff roles, editing staff and on-duty on the dashboard; editing in any state on Android (`Routes.kt`'s `editable()` still shows „Editează” only for `draft` and `submitted`, and its comment goes stale); labels for `withdrawn` in both apps.
- Pagination of `GET /seniors/{id}/calls`.

## 10. Calls made while writing this

Small choices nobody was asked about. Check them while reading:

1. Staff writes that can race take one advisory lock (§5.3).
2. `PUT /staff/on-duty`, `DELETE /staff/on-duty` and `POST …/signature` answer 204 with no body.
3. `not_medic` is a new reason, not FastAPI's validation 422, because only the database knows whether someone holds `medic`.
4. A withdrawal recorded by DAS uses a new consent method, `das`, so the history says who recorded it.
5. A withdrawal's `text_version` is copied from the latest consent row, or `"none"` if there is none.
6. A draft's delete refuses on any remaining foreign-key reference instead of checking calls by name (§5.4).
7. Transcripts of `test` calls are served. Only the call list hides them.
8. Calls get their own package, `app/calls/`, for the import graph (§5.5).
9. `phone_taken` applies on create and when an edit changes the number, not on every save. A legacy shared-mobile senior stays editable (§5.2).
