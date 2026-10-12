# Seniors and enrollment

**Status:** approved design · 2026-10-12 · branch `auth-layer`
**Issues:** #16 (parent), #17, #18, #19, #21.
**Implements:** UC-01 (register a senior), UC-04 step 1 (accept, without the welcome call), UC-14 (the „Personal” screen), the per-role homes of UC-02 and UC-12 on Android, [auth-layer.md](auth-layer.md) §3.6 and the seniors and staff rows of its §10, [04 §1 and §2](sentinela/04-interfaces.md).
**Read with:** the system spec in [sentinela/](sentinela/README.md) and [auth-layer.md](auth-layer.md). Where either disagrees with this file about the endpoints defined here, this file wins, and slice 1 brings them in line (§6.6).

Sections 1 to 5 are shared reference that every slice reads. Sections 6 to 9 are self-contained briefs, one per pull request, each ending on a completion criterion. Section 10 is the rollout.

## 1. Outcome

A medic registers a senior with caregivers, DAS accepts the senior, and each number reaches only the seniors its grants cover. The work is done when this runs on the local stack with Firebase test numbers:

1. DAS, `+40700000001`, opens „Personal” on the dashboard and adds `+40700000002` as a medic.
2. The medic signs in on Android, opens „Pacient nou”, registers „doamna Maria” with the caregiver `+40700000004`, and submits.
3. The caregiver signs in on a second emulator and sees doamna Maria. Their `GET /me` names her.
4. Another medic gets 404 for her.
5. DAS could not see her as a draft, sees her once she is submitted, and accepts her. A second accept is refused.
6. The medic removes the caregiver. The caregiver's next request answers `not_registered` and the app signs them out.

## 2. Decisions

| ID | Decision | Note |
|---|---|---|
| SE1 | In scope: the reach rule; the senior, caregiver and enrollment endpoints; `GET /staff`; the `/me` additions; the dashboard's „Personal” screen; Android navigation with a home per role; the medic's „Pacient nou” form | Out of scope: §11 |
| SE2 | No migration. The `seniors` table, the foreign key on `grants.senior_id` and the one-senior-grant index shipped in `741f75a7dbe1`, and `tests/test_models.py` already tests both constraints | #16's first task is done; its note about #15 is stale, because the head is `b3e9c1d47a52` |
| SE3 | A draft needs a full name, a form of address and a valid phone number | The table's NOT NULL columns |
| SE4 | Submitting also needs a street and a street number. Caregivers are optional | DAS must be able to find the door (G13); a senior with no family can still be enrolled |
| SE5 | The reach rule of auth-layer §3.6 is one SQL condition, `reaches(caller, *roles)`, used by every list and every single lookup | A list and a lookup cannot disagree |
| SE6 | `GET /seniors?role=` narrows the list to one role's reach. A role the caller does not hold gives an empty list, not a refusal | The union stays the permission (AL2); the filter only picks what a home shows |
| SE7 | A senior has one response shape for every role. Everyone who reaches a senior sees the caregivers, phone numbers included | Family can call each other |
| SE8 | The API puts no limit on the number of caregivers | UC-01's "one or two" is guidance for the medic |
| SE9 | The medic who registered a senior, and DAS for a senior it reaches, may edit the registration and the caregivers in any state. Creating and submitting are the medic's; accepting is DAS's | Departs from 04 §2 and #16, which say medic only and `draft` only |
| SE10 | One mobile number, one senior. A mobile that already signs in as another senior is refused with `phone_taken`. A landline can be shared, because it signs nobody in | Replaces AL7's sentence about a couple sharing a mobile. The index stays and is what enforces this |
| SE11 | The senior's grant follows the senior's number: made for a mobile, moved when the number changes, removed when the number becomes a landline | 04 §2 |
| SE12 | One number may be both the senior and a caregiver of that senior | 01 §6: "a senior who uses a relative's phone" |
| SE13 | A repeated submit or accept is refused with `wrong_state` | #18. Unlike taking an incident, where the same person repeating gets a 200 |
| SE14 | `POST /seniors` is not repeat-safe: two posts make two drafts. The form switches to `PUT` after its first save and disables its button while a request is in flight | An exception to 04 §0. Two seniors can share a landline, so nothing identifies a duplicate |
| SE15 | Nobody is stored as the accepter. The accept is logged with the user id | No column exists for it |
| SE16 | The senior, caregiver and enrollment routes live in `app/seniors.py` on their own router, included into `api` | Rewords the rule in `backend/AGENTS.md`; `main.py` would otherwise double in size |
| SE17 | The dashboard adopts react-router | The rule in `dashboard/AGENTS.md`: add a router with the first feature that needs it |
| SE18 | Android adopts Navigation Compose with type-safe routes | The rule in `android/AGENTS.md` |
| SE19 | „Pacient nou” is four steps: senior, address, caregivers, review. Each „Continuă” saves | Chosen from mockups |
| SE20 | The medic's home is a grid of cards. A senior's page and the form open full screen, on a tablet and on a phone | No adaptive list-detail library in this round |
| SE21 | Delivery: this one spec, four plans, four pull requests: backend, dashboard, Android homes, Android form | §10 |

**Departures from the system spec and the issues**, made consistent by §6.6:

| Where | Change |
|---|---|
| #16, first task and its note | Already on `main` (SE2) |
| #16 and 04 §2, "Save senior draft" | Editable by the medic or by DAS, in any state (SE9) |
| 04 §2, "Add or remove a caregiver" | DAS may do it too (SE9). No notice SMS yet |
| 01 §6, "Who grants" | DAS may also add and remove a senior's caregivers (SE9) |
| auth-layer AL7, 01 §6, 05 §3 | The shared-mobile case is refused (SE10) |
| 04 §0 | Two new refusal reasons (§3.2); `POST /seniors` is the one command that is not repeat-safe (SE14) |
| 04 §1 | `GET /seniors` takes `role`; seniors carry the fields that exist today; `GET /staff` returns roles and no on-duty flag yet |
| #17, "Done when" | The staging check is a person's step (§10); an agent checks on the local stack |
| #21, medic home | The „Pacient nou” button arrives with #19, so `main` never has a button that leads nowhere |
| `dashboard/AGENTS.md` | It says CI does not run Vitest. CI does (`npx vp test` in `dashboard.yml`) |

## 3. Shared contract

Every endpoint is under `/api` and follows auth-layer §3.1 for identity.

### 3.1 Reach

`reaches(caller, *roles)` is an SQL condition over `seniors`. With no role named, every role the caller holds counts.

| Role | Reaches |
|---|---|
| `medic` | Seniors whose `medic_id` is the caller's id, while the caller holds a medic grant |
| `caregiver` | The seniors named by the caller's caregiver grants |
| `senior` | The senior named by the caller's senior grant |
| `das` | Every senior whose state is not `draft` |

A caller who holds none of the named roles reaches nothing.

| Request | Roles that count |
|---|---|
| `GET /seniors` | All, or the one named in `role` |
| `GET /seniors/{id}` | All |
| `PUT /seniors/{id}`, add or remove a caregiver | `medic`, `das` |
| `POST /seniors/{id}/submit` | `medic` |
| `POST /seniors/{id}/accept` | `das` |

**A request is checked in this order**, and the first failure answers:

1. Identity: 401 `not_signed_in`, 403 `not_registered`.
2. Role: 403 `not_allowed` when the caller holds none of the roles the request accepts.
3. Body: FastAPI's standard 422.
4. Reach: 404 `not_found` (AL8).
5. State: 409 `wrong_state`, then 422 `missing_fields`, then 409 `phone_taken` or `already_done`.

### 3.2 Refusals

The body and the existing reasons are auth-layer §3.2. Two reasons are new:

| HTTP | `reason` | When | The client then |
|---|---|---|---|
| 422 | `missing_fields` | Submitting a senior without a street or a street number, or an edit that would empty either on a senior past `draft`. The body adds `fields`, the missing column names: `{"detail": {"reason": "missing_fields", "fields": ["street", "street_number"]}}` | Names the missing fields |
| 409 | `phone_taken` | Saving a senior with a mobile number that already holds a senior grant for another senior (SE10) | Shows „Acest număr este deja al altui senior.” |

Existing reasons, as these endpoints use them:

| HTTP | `reason` | When |
|---|---|---|
| 404 | `not_found` | A senior outside the caller's reach, or removing a caregiver who is not this senior's |
| 409 | `wrong_state` | Submitting a senior that is not `draft`; accepting one that is not `submitted` |
| 409 | `already_done` | Adding a caregiver who already is this senior's caregiver |

### 3.3 Reads

**`GET /seniors?role=`.** Any caller with a grant. `role` is optional and one of `das`, `medic`, `caregiver`, `senior`; anything else is a 422. Newest first.

```json
[
  {
    "id": "0199b6f0-7c1e-7a55-b8d2-5d0c8c3a7f21",
    "full_name": "Maria Popescu",
    "form_of_address": "doamna Maria",
    "phone_e164": "+40256123456",
    "phone_is_landline": true,
    "enrollment_state": "draft"
  }
]
```

**`GET /seniors/{id}`.** Any caller who reaches the senior. The row above, plus:

```json
{
  "street": "Str. Daliei",
  "street_number": "12",
  "block": "B3",
  "staircase": "A",
  "floor": "2",
  "apartment": "9",
  "intercom_code": "09",
  "key_holder": "vecina de la ap. 10",
  "landmark": null,
  "call_window": "9-12",
  "medic": { "display_name": "Dr. Ion Pop", "practice": "CMI Dr. Pop" },
  "caregivers": [
    {
      "user_id": "0199b6f0-8d3a-7c10-9e4f-2a1b3c4d5e6f",
      "display_name": "Ioana Pop",
      "relation": "fiică",
      "phone_e164": "+40700000004"
    }
  ]
}
```

Caregivers are sorted by name. This object is called **the senior's page** below.

**`GET /enrollments`.** DAS. The rows of `GET /seniors`, only seniors in `submitted`, oldest first.

**`GET /staff`.** DAS. Everyone who holds a `das` or a `medic` grant, sorted by name. `roles` lists only those two roles, `das` first.

```json
[
  {
    "id": "0199b6f0-9a2b-7d31-8c5e-1f2a3b4c5d6e",
    "display_name": "Dr. Ion Pop",
    "phone_e164": "+40700000002",
    "practice": "CMI Dr. Pop",
    "roles": ["medic"]
  }
]
```

**`GET /me`.** Each grant gains two fields, `null` where they do not apply (auth-layer §3.3, optional additions):

```json
{ "role": "caregiver", "senior_id": "0199b6f0-7c1e-7a55-b8d2-5d0c8c3a7f21", "senior_form_of_address": "doamna Maria", "relation": "fiică" }
```

### 3.4 Commands

| Request | Who | Effect | Answers | Refused |
|---|---|---|---|---|
| `POST /seniors` | Medic | Creates a senior in `draft`, registered by the caller | 201, the page | 409 `phone_taken` |
| `PUT /seniors/{id}` | Medic or DAS, in reach | Replaces every registration field | 200, the page | 422 `missing_fields`, 409 `phone_taken` |
| `POST /seniors/{id}/caregivers` | Medic or DAS, in reach | Makes the caregiver grant | 201, the caregiver as in the page | 409 `already_done` |
| `DELETE /seniors/{id}/caregivers/{user_id}` | Medic or DAS, in reach | Deletes that caregiver grant | 204 | 404 `not_found` |
| `POST /seniors/{id}/submit` | Medic, in reach | `draft` → `submitted` | 200, the page | 409 `wrong_state`, 422 `missing_fields` |
| `POST /seniors/{id}/accept` | DAS, in reach | `submitted` → `accepted`. Queues nothing yet | 200, the page | 409 `wrong_state` |

A refused command changes nothing: its transaction rolls back.

### 3.5 Bodies and rules

**The senior body**, the same for `POST` and `PUT`:

| Field | Rule |
|---|---|
| `full_name` | Required, 1 to 200 characters after trimming |
| `form_of_address` | Required, 1 to 120 characters after trimming |
| `phone` | Required. It must parse with `normalize()` (auth-layer §3.5); a landline is fine. Stored as E.164. `phone_is_landline` is `not is_mobile()` |
| `street`, `key_holder`, `landmark` | Optional, at most 200 characters |
| `street_number`, `block`, `staircase`, `floor`, `apartment` | Optional, at most 20 characters |
| `intercom_code` | Optional, at most 40 characters |
| `call_window` | Optional, at most 60 characters, free text |

Optional fields are trimmed, and an empty one is stored as `null`. `PUT` replaces every field, so a field left out becomes `null`.

**The caregiver body:**

| Field | Rule |
|---|---|
| `display_name` | Required, 1 to 120 characters after trimming |
| `relation` | Required, 1 to 60 characters after trimming |
| `phone` | Required. It must parse and be a mobile, because a caregiver signs in by SMS |

**The senior's grant** (SE10, SE11):

| Situation | Result |
|---|---|
| A mobile number with no senior grant | The user row is made if the number has none, named with the first 120 characters of the senior's full name, which is what `users.display_name` holds; a user that exists keeps their name. A `senior` grant for this senior is made, with `granted_by` the caller |
| A mobile number that holds a senior grant for another senior | 409 `phone_taken` |
| A landline | No user row and no grant |
| `PUT` changes the number | The senior grant for this senior is deleted, then the rows above apply to the new number |
| `PUT` keeps the number | The grant is untouched |

A later change of the senior's name does not rename their user row.

**Caregiver grants:**

| Situation | Result |
|---|---|
| A new number | The user row is made with the body's name, and a `caregiver` grant with the relation and `granted_by` the caller |
| A known number | The grant is added; the user keeps their name |
| Already this senior's caregiver | 409 `already_done`. The relation is not updated |
| Two adds of one number at the same moment | The insert is `ON CONFLICT DO NOTHING`, so the loser gets 409 `already_done` |
| Remove | Only that caregiver grant is deleted. The user row stays. With no other grant, their next request answers `not_registered` |

**Transitions** change the state only where it is still the expected one, so of two submits or two accepts at once, one wins and the other gets `wrong_state`.

## 4. Data

No table changes (SE2). Each field of §3.3 is the `seniors` column of the same name ([05](sentinela/05-data-model.md)). `medic` comes from `users` through `seniors.medic_id`, and `caregivers` from `grants` with role `caregiver`.

## 5. Test numbers

Auth-layer §5 lists four. This work adds two, configured by a person in the Firebase console:

| Number | Code | Used as |
|---|---|---|
| `+40700000004` | `444444` | A caregiver |
| `+40700000005` | `555555` | A senior |

A test number is enough for a senior here, because nothing dials it yet. When calls arrive, a senior with a test number must not be dialled (auth-layer §5).

## 6. Slice 1: Backend

**Branch:** `auth-layer`, which carries this spec and is level with `main`. **Closes:** #16, #18. **Read first:** [backend/AGENTS.md](../../backend/AGENTS.md), then §1 to §5 of this file.

### 6.1 Files

| File | Holds |
|---|---|
| `app/grants.py` | `user_for_number(session, phone_e164, display_name) -> User`: the insert-if-missing step now inside `staff.py`, shared by staff, senior and caregiver grants |
| `app/staff.py` | `grant_staff()` calls `user_for_number()`. Gains `list_staff(session)` for `GET /staff` |
| `app/reach.py` | `reaches(caller, *roles)` and `reachable_senior(session, caller, senior_id, *roles) -> Senior`, which raises 404 `not_found` (§3.1) |
| `app/seniors.py` | An `APIRouter` with the reads and commands of §3.3 and §3.4 for seniors, caregivers and enrollment; their request and response models; the grant rules of §3.5 |
| `app/main.py` | `GET /staff`; the `/me` additions; `api.include_router(seniors.router)` |
| `tests/conftest.py` | `add_senior` accepts the medic who registers the senior |
| `tests/test_reach.py`, `test_seniors.py`, `test_caregivers.py`, `test_enrollment.py` | §6.4 |
| `tests/test_staff.py`, `tests/test_me.py` | The `GET /staff` and `/me` cases of §6.4 |

### 6.2 Facts that are hard to find by looking

- **The table is already there.** Do not generate a migration. `alembic check` must report no difference after this slice.
- **`include_router` copies routes when it is called.** `api.include_router(seniors.router)` goes before `app.include_router(api)` at the bottom of `main.py`.
- **`enrollment_state` is a `StoredEnum`.** Compare with enum members, as in `Senior.enrollment_state != EnrollmentState.draft`. A state name this copy does not know reads back as a string, and DAS reaches it because it is not `draft`.
- **`Grant.role` is a plain string column** with a CHECK; `Caller.roles` is a set of `Role`.
- **`Caller.grants` already holds every grant**, so `reaches()` needs no query of its own.
- **The test database is emptied by `TRUNCATE grants, users CASCADE`**, which also empties `seniors` through its foreign key.
- **`add_senior` makes a new medic for every senior.** Tests of "own senior" need to name the medic.
- **`incident_view.py` has a `SeniorDetail` and a `caregivers_query`** for the incident screen. The senior's page has more fields and a `user_id` per caregiver, so it gets its own models; do not change the incident response.
- **Refusals are logged** with the reason and the user id, never a full number (AL15).

### 6.3 Steps

Each step is done when its criterion holds.

1. **`app/grants.py`.** *Done:* `tests/test_staff.py` passes unchanged.
2. **`app/reach.py`.** *Done:* the reach table of §6.4 passes.
3. **`GET /seniors` and `GET /seniors/{id}`.** *Done:* their read cases pass.
4. **`POST /seniors` and `PUT /seniors/{id}`**, with the senior's grant. *Done:* the senior cases pass.
5. **Caregivers.** *Done:* the caregiver cases pass.
6. **Submit, accept and `GET /enrollments`.** *Done:* the enrollment cases pass.
7. **`/me` additions.** *Done:* the `/me` cases pass. Existing assertions that compare a whole grant, in `tests/test_me.py` and `tests/test_staff.py`, gain the two new fields.
8. **`GET /staff`.** *Done:* the staff cases pass.
9. **Docs.** *Done:* every row of §6.6 is changed.
10. **Real-token check.** On Compose, with tokens from `dev_token.py`, run the story of §1 steps 2 to 6 with curl. *Done:* each step's answer is reported. If `+40700000004` is not yet a test number in the console, stop and report it.

### 6.4 Test checklist

The stand-in verifier and the fixtures are those of auth-layer §6.4.

**Refusal matrix.** The first two rows apply to every endpoint of §3.3 and §3.4. The third applies to every endpoint that names a role. The fourth applies to every endpoint that takes a senior's id.

| Caller | Expected |
|---|---|
| No header, `invalid`, `no-phone` | 401 `not_signed_in` |
| An unknown number, a user with zero grants | 403 `not_registered` |
| A caller without a role the request accepts | 403 `not_allowed` |
| A caller with the role, outside reach | 404 `not_found` |

**Reach**, as a table of caller against senior:

| Caller | Draft | Submitted |
|---|---|---|
| The medic who registered her | Reaches | Reaches |
| Another medic | No | No |
| That medic, after the medic grant is deleted | No | No |
| Her caregiver; herself | Reaches | Reaches |
| A caregiver of another senior | No | No |
| DAS | No | Reaches |

- `GET /seniors` returns exactly the seniors the table gives each caller.
- `role=caregiver` for a medic who is also a caregiver returns only the senior they care for; `role=das` for that caller returns `[]`; `role=nurse` is a 422.

**Seniors**
- A medic creates a draft with only the three required fields; the page comes back with `null` for the rest.
- A landline sets `phone_is_landline` and makes no user and no grant. A mobile makes the user and the senior grant, and that number's `/me` names the senior.
- A full name of 150 characters makes a user named with its first 120.
- A blank name, a blank form of address, an unparseable number and an over-long field are each a 422.
- A mobile that is another senior's is 409 `phone_taken`, and no senior is created.
- Two seniors with the same landline are both created.
- `PUT` from a mobile to another mobile moves the grant; to a landline removes it; with the same number keeps the same grant row.
- `PUT` by DAS on a submitted senior succeeds; on a draft it is 404.
- `PUT` that empties the street on a submitted senior is 422 `missing_fields`; on a draft it succeeds.
- A caregiver calling `PUT` gets 403 `not_allowed`.

**Caregivers**
- Adding makes the user and the grant with its relation; the caregiver's `GET /seniors` returns only this senior.
- A known number keeps its name. A landline is a 422.
- A repeat is 409 `already_done`. Two adds at once give one 201 and one 409.
- The senior's own mobile can be added as a caregiver (SE12).
- Removing answers 204; that number's next request is 403 `not_registered`. A caregiver who is also a medic keeps the medic grant.
- Removing a user who is not this senior's caregiver is 404.
- DAS adds and removes a caregiver on a submitted senior.

**Enrollment**
- Submit moves a complete draft to `submitted`. Without a street or number it is 422 `missing_fields` with both names in `fields`. A second submit is 409 `wrong_state`.
- DAS gets 404 for a draft and 200 after the submit; `GET /enrollments` lists the senior.
- Accept moves her to `accepted` and `GET /enrollments` no longer lists her. A second accept is 409 `wrong_state`.
- A medic calling accept, and DAS calling submit, each get 403 `not_allowed`.
- Two accepts at once give one 200 and one 409.

**`/me`**
- A caregiver grant carries the senior's form of address and the relation. A `das` grant carries `null` for both.

**`GET /staff`**
- A person with both roles is one row with `["das", "medic"]`. A caregiver is not listed. A medic calling it gets 403 `not_allowed`.

**The story of §1**, steps 2 to 6, as one test through the API.

### 6.5 Completion criterion

Slice 1 is done when all of these hold:
- Every item in §6.4 passes in `uv run pytest`.
- `uv run ruff check .` and `uv run ruff format --check .` pass.
- `alembic check` reports no difference.
- Every row of §6.6 is changed.
- Step 10 is reported with its result.

Open the PR only when the person who dispatched you asks for it.

### 6.6 Spec and config changes in this PR

| File | Change |
|---|---|
| `docs/specs/sentinela/04-interfaces.md` §0 | The reasons `missing_fields` and `phone_taken`; `POST /seniors` as the exception to repeat-safe |
| same file, §1 | The seniors rows match §3.3 and say which fields arrive later; `GET /enrollments`; `GET /staff` returns roles, with on duty to come |
| same file, §2 | The senior, caregiver, submit and accept rows match §3.4 and SE9; the notice SMS and the welcome call are marked as not built |
| `docs/specs/sentinela/01-architecture.md` §6 | DAS may add and remove caregivers and edit a registration (SE9); one mobile, one senior (SE10) |
| `docs/specs/sentinela/02-use-cases.md` UC-01 | Step 6 names what a submit needs (SE4) |
| `docs/specs/sentinela/05-data-model.md` §3 | The one-senior-grant row matches SE10 |
| `docs/specs/auth-layer.md` | AL7 and §3.6 match SE10 and SE9; §3.3 shows the two new grant fields; §5 lists the two new numbers; §10 marks the seniors row and `GET /staff` as built here |
| `backend/AGENTS.md` | The layout gains `grants.py`, `reach.py` and `seniors.py`; the route rule allows a router included into `api` |

## 7. Slice 2: Dashboard

**Branch:** `staff-dashboard`, in its own worktree, cut from `main` after slice 1 has merged. **Closes:** #17. **Read first:** [dashboard/AGENTS.md](../../dashboard/AGENTS.md), then §1 to §5 of this file.

### 7.1 Behaviour

| File | Holds |
|---|---|
| `package.json` | `react-router`, added with `npm install react-router` |
| `src/main.tsx` | `App` inside a `BrowserRouter` |
| `src/App.tsx` | The signed-in view becomes a header with two links and the routes. Sign-in stays a gate above them |
| `src/Staff.tsx` | The „Personal” screen |
| `src/api.ts` | The `Staff` type, `fetchStaff()` and `grantStaff(body)`. `ApiError` also carries the field names of a 422 |
| `src/refusals.ts`, `src/refusals.test.ts` | `staffError(error) -> string`: the Romanian text for a refused add |
| `src/labels.ts` | The role labels |
| `AGENTS.md` | The layout; react-router is the router; CI runs Vitest |

**Routes**

| Path | Shows |
|---|---|
| `/` | The incident board |
| `/personal` | „Personal” |
| Anything else | Redirects to `/` |

Caddy already serves `index.html` for unknown paths, so a reload on `/personal` works.

**„Personal”** shows a table of `GET /staff` above a form that posts to `POST /staff`.

- **The form** asks for the name, the phone number, the role, and the practice. The practice field appears only for a medic.
- **„Adaugă” is enabled** when the name and the phone are filled, and for a medic the practice too.
- **The phone number** goes through `toE164()` from `phone.ts` before it is sent.
- **After a 201** the list is read again, the form clears, and a notice names the person.
- **The list is read** when the screen opens and after each add. There is no timer.

**A 422 from FastAPI** has the body `{"detail": [{"loc": ["body", "phone"], ...}]}`. The last item of `loc` names the field.

| Answer | Text |
|---|---|
| 409 `already_done` | „Numărul are deja acest rol.” |
| 422 on `phone` | „Număr de telefon invalid. Trebuie să fie un număr de mobil.” |
| 422 on `practice` | „Completați cabinetul medicului.” |
| 422 on `display_name` | „Completați numele.” |
| Anything else | „Nu s-a putut salva. Încercați din nou.” |

**Romanian copy**

| Element | Text |
|---|---|
| Header links | „Incidente”, „Personal” |
| Table columns | „Nume”, „Telefon”, „Rol”, „Cabinet” |
| Role labels | `das` „Dispecer DAS”, `medic` „Medic” |
| Form title | „Adaugă personal” |
| Field labels | „Nume”, „Număr de telefon”, „Rol”, „Cabinet” |
| Button | „Adaugă” |
| After an add | „{name} a fost adăugat.” |
| Empty list | „Nu există personal.” |
| List failed to load | „Lista nu a putut fi încărcată.” |

### 7.2 Completion criterion

Slice 2 is done when all of these hold:
- `npx vp check`, `npx vp build` and `npx vp test` pass, including the test of `staffError`.
- On `localhost:5173` against Compose, signed in as `+40700000001`:
  - „Personal” lists the staff.
  - Adding a medic shows them in the list.
  - Adding the same number and role again shows the `already_done` text.
  - A landline shows the phone text.
  - A reload on `/personal` stays on „Personal”.
- That medic's number gets a 200 from `GET /api/me` with a `medic` grant, using a token from `dev_token.py`.

Report each of these observations. Open the PR only when the person who dispatched you asks for it.

## 8. Slice 3: Android navigation and homes

**Branch:** `android-homes`, in its own worktree, cut from `main` after slice 1 has merged. **Closes:** #21. **Read first:** [android/AGENTS.md](../../android/AGENTS.md), [android/app/AGENTS.md](../../android/app/AGENTS.md), then §1 to §5 of this file.

**Preconditions:** the shared keystore and `sentinela.apiUrl=http://10.0.2.2:8000` in `local.properties`; the test numbers granted on the local stack, with one senior and one caregiver registered through the API.

### 8.1 Build

Through `gradle/libs.versions.toml`, on `:app` only.

| Addition | Note |
|---|---|
| `androidx.navigation:navigation-compose`, the current stable release | Type-safe routes use the serialization plugin the app already has |
| `BuildConfig.REREAD_SECONDS` | 30. A debug build reads `sentinela.rereadSeconds` from `local.properties`, so a demo can use 10 (06 §3) |

If Navigation cannot build under AGP 9.4.1 and Kotlin 2.2.10, stop and report the build error.

### 8.2 Structure

- **Sign-in stays as it is.** `AuthViewModel` and its `Screen` states are unchanged up to `Screen.Home`.
- **`Screen.Home` hosts a `NavHost`** in place of the placeholder. Its start destination is the role's home, and it is rebuilt when the role changes.
- **Every home has a menu** with „Schimbă rolul”, when there are several roles, and „Ieșire”.

| Role | Home | Reads |
|---|---|---|
| `medic` | „Pacienții mei”: a grid of cards, one column on a phone and two on a tablet | `GET seniors?role=medic` |
| `caregiver` | „Seniorii mei”: the same grid | `GET seniors?role=caregiver` |
| `senior` | Their own page | `GET seniors?role=senior`, then `GET seniors/{id}` for its one row |
| `das` | An empty state, until incidents exist | Nothing |

- **A card** shows the form of address, the full name and number, and the enrollment state.
- **Tapping a card** opens the senior's page full screen, with a back arrow.
- **The senior's page** shows everything `GET seniors/{id}` returns: the form of address and state, the name and number with a „fix” mark for a landline, the address and access details, the call window, the medic, and the caregivers with relation and number. It is the same for every role.

**`SentinelaApi`** gains `seniors(role)` and `senior(id)`. Their models keep `enrollment_state` as a string (app/AGENTS.md: decode leniently).

**What a list or a page shows for each answer**, as a pure function tested on the JVM:

| Answer | Nothing on screen yet | Data on screen |
|---|---|---|
| 200 | The data | The new data |
| No connection, or a 5xx | „Fără conexiune.” with „Reîncercați” | The last data, under a „Fără conexiune” banner (06 §1) |
| 404 | „Nu a fost găsit.” | „Nu a fost găsit.” |
| 403 `not_allowed` | „Nu aveți acces la această acțiune.” | The same |
| 401, after the retry | The phone screen | The phone screen |
| 403 `not_registered` | The phone screen with the not-registered text, signed out | The same |

The last row is how a grant revoked mid-session ends the session. The reason is read from the refusal body, `{"detail": {"reason": ...}}`.

**The timed re-read.** While a list or a page is on screen, it is read again every `REREAD_SECONDS`. The timer stops when the screen leaves the foreground.

**Romanian strings**, in `strings.xml`:

| Key | Text |
|---|---|
| Medic home | „Pacienții mei” |
| Caregiver home | „Seniorii mei” |
| DAS home | „Nu sunt incidente.” |
| Empty list | „Nu aveți niciun senior.” |
| States | `draft` „Ciornă”, `submitted` „Trimis la DAS”, `accepted` „Acceptat”, `active` „Activ”, `refused` „Refuzat”, `wrong_number` „Număr greșit”, `unreachable` „De negăsit”. An unknown state shows no label |
| Landline mark | „fix” |
| Page sections | „Adresă și acces”, „Interval pentru apel”, „Medic”, „Aparținători” |
| No caregivers | „Niciun aparținător.” |
| Banner | „Fără conexiune” |
| Failures | „Fără conexiune.”, „Nu a fost găsit.”, „Nu aveți acces la această acțiune.” |

**`android/AGENTS.md`'s rule changes:** Navigation Compose is the navigation library; Room still arrives with the first feature that needs it.

### 8.3 Completion criterion

Slice 3 is done when all of these hold:
- CI's command `./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug` passes, including JVM tests for which home each role gets and for every cell of the table above.
- A release build installs and launches on an emulator (R8).
- On an emulator against the local stack:
  - A caregiver sees their senior, and the page behind the card.
  - A medic sees their list, drafts included.
  - A senior lands on their own page.
  - Switching roles switches homes.
  - Airplane mode shows the banner over the last list.
  - Deleting the caregiver's grant signs them out with the not-registered text at the next re-read.

Report each of these observations, with screenshots from `android screen capture`. Open the PR only when the person who dispatched you asks for it.

## 9. Slice 4: Android „Pacient nou”

**Branch:** `android-pacient-nou`, cut from `main` after slices 1 and 3 have merged. **Closes:** #19. **Read first:** the same files as slice 3, then §1 to §5 of this file.

### 9.1 Entry points

All on the medic's screens, and all open one destination, the form:

| From | Opens |
|---|---|
| „Pacient nou”, a button on the medic's home | An empty form |
| Tapping a draft's card on the medic's home | The form filled from `GET seniors/{id}`, at step 1 |
| „Editează”, on the page of a senior the medic opened from their home | The same, for a senior in any state (SE9) |

### 9.2 The four steps

| Step | Fields | „Continuă” |
|---|---|---|
| 1 · „Senior” | Full name, form of address, phone number, call window | Enabled when the first three are valid. Creates the senior with `POST seniors` the first time, and saves with `PUT seniors/{id}` after that |
| 2 · „Adresă și acces” | Street, number, block, staircase, floor, apartment, intercom code, key holder, landmark | Saves with `PUT`. A draft may leave the street and number empty; past `draft` they are required |
| 3 · „Aparținători” | The caregivers so far, each with a remove button, and a row to add one: name, relation, phone number | Sends nothing. „Adaugă” and remove each call the API at once |
| 4 · „Verificare” | A read-only summary from `GET seniors/{id}`, and what is still missing | A draft: „Trimite la DAS”, enabled when the street and number are filled; it submits and returns to the home. Past `draft`: „Gata” returns to the page |

- **`PUT` sends the whole registration** (§3.5), so the form keeps the fields of steps 1 and 2 together and sends both at each save.
- **Back** goes to the previous step, and from step 1 leaves the form. What „Continuă” saved stays saved; what was typed since is dropped.
- **A request in flight** disables „Continuă”, „Adaugă” and „Trimite la DAS” (SE14).

**`SentinelaApi`** gains `createSenior`, `updateSenior`, `addCaregiver`, `removeCaregiver` and `submit`.

### 9.3 Validation and refusals

**Validation** is a pure function tested on the JVM. It mirrors §3.5: required fields are not blank after trimming, no field is over its limit, and a phone number is a `+` and 8 to 15 digits after `toE164()`. The server decides whether the number is real.

**A refusal** is read by one pure function that understands both bodies: FastAPI's 422, `{"detail": [{"loc": [...]}]}`, and ours, `{"detail": {"reason": ...}}`.

| Answer | Shown |
|---|---|
| 422 on the senior's `phone` | Under the field: „Număr de telefon invalid.” |
| 409 `phone_taken` | Under the field: „Acest număr este deja al altui senior.” |
| 422 on a caregiver's `phone` | Under the field: „Număr invalid. Aparținătorul are nevoie de un număr de mobil.” |
| 409 `already_done` | „Este deja aparținător pentru acest senior.” |
| 422 `missing_fields` | On step 4, the missing fields by their labels |
| 409 `wrong_state` | The senior is read again, and step 4 shows the state it is in |
| 404, 403 `not_allowed`, no connection, 401, 403 `not_registered` | As in slice 3's table. The form keeps what was typed when there is no connection |

### 9.4 Layout

One column of fields, at most 600 dp wide and centred on a tablet, full width on a phone. Above it, „Pasul 2 din 4” and the step's name; on a wide screen, the four step names in a row with the current one marked.

**Romanian strings**, in `strings.xml`:

| Key | Text |
|---|---|
| Title, and the home's button | „Pacient nou” |
| Edit button | „Editează” |
| Step names | „Senior”, „Adresă și acces”, „Aparținători”, „Verificare” |
| Step counter | „Pasul %1$d din %2$d” |
| Step 1 fields | „Nume complet”, „Formulă de adresare”, „Număr de telefon”, „Interval preferat pentru apel” |
| Form of address hint | „de exemplu: doamna Maria” |
| Step 2 fields | „Stradă”, „Număr”, „Bloc”, „Scară”, „Etaj”, „Apartament”, „Interfon”, „Cine are cheie”, „Reper” |
| Step 3 fields | „Nume”, „Relație”, „Număr de telefon” |
| Buttons | „Continuă”, „Înapoi”, „Adaugă”, „Elimină”, „Trimite la DAS”, „Gata” |
| Missing | „Lipsesc: %1$s” |
| Sent | „Trimis la DAS.” |
| The refusal texts | As in §9.3 |

### 9.5 Completion criterion

Slice 4 is done when all of these hold:
- CI's command passes, including JVM tests for the validation, for reading both refusal bodies, and for what each step's „Continuă” sends.
- A release build installs and launches on an emulator (R8).
- On an emulator against the local stack:
  - The medic registers „doamna Maria” with one caregiver and submits.
  - The caregiver's test number, on a second emulator, sees her.
  - Leaving after step 1 and tapping the draft's card reopens it with its data.
  - „Editează” on a submitted senior saves a changed address.
  - A caregiver with a landline shows the text under the field.

Report each of these observations, with screenshots. Open the PR only when the person who dispatched you asks for it.

## 10. Rollout

Steps marked *person* are done by a team member; agents leave cloud environments alone (root `AGENTS.md`).

1. *Person.* Add the two test numbers of §5 in the Firebase console.
2. Slice 1 merges to `main`. Staging redeploys `api`; there is no migration.
3. Slices 2 and 3 run in parallel, each in its own worktree and pull request.
4. Slice 4 starts after slice 3 has merged.
5. *Person.* On staging, a DAS test number adds a medic from the dashboard, sees them in the list, and that number signs in on Android as a medic (#17's "Done when").

Each slice is one folder, so a red Android build never holds back an API deploy (root `AGENTS.md`).

## 11. Later, outside this work

| Item | Belongs to |
|---|---|
| The notice SMS to a new caregiver | Spike S10 |
| The code, reason, calls, consent, watch and home node fields on the senior reads | Their features; each is an optional addition |
| The welcome call on accept, and every state after `accepted` | UC-04 |
| „Cereri de înrolare” and the senior screens on the dashboard, where DAS would use its edit right | The dashboard work |
| On duty: `PUT /staff/on-duty`, the flag in `GET /staff` | The hand-over work (P10) |
| A refresh push when a caregiver is added or removed | The push work (G4) |
| The signature on the tablet | Optional (G7) |
| Red incidents in the Android DAS role | UC-11 |
| „Sunați-mă” and the watch relay | UC-09, UC-10 |
| Who accepted a senior, and when it was submitted | With the screen that needs them; each needs a column |
| A list beside the patient on a tablet | UC-12's panel of codes |
| Renaming the senior's user row when the senior's name is corrected | When a screen shows that name |

## 12. Facts still to confirm

| Fact | Confirmed by |
|---|---|
| FastAPI answers a role refusal before it validates the body (§3.1 order) | A test in slice 1 |
| The stable Navigation Compose release that builds with AGP 9.4.1 and Kotlin 2.2.10 | Slice 3's first step |
| react-router's current major version and its import path | Slice 2's first step |
| The two new test numbers and codes match the console | The person, when configuring |
