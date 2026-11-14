# Senior Equipment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The medic records a senior's equipment at registration. DAS and the phone apps show only the devices the senior has, and warn about a declared device that has never reported.

**Architecture:** The backend owns the data and the rules:

- One nullable `seniors.equipment` text array, carried on `SeniorForm` and `SeniorView`.
- An `app_signed_in` flag on `GET /seniors/{id}`.

Each client (dashboard, Android, iOS) has one pure helper that turns `equipment`, `watch_state`, `app_signed_in` and `enrollment_state` into "show the watch panel?" and a list of device warnings. The screens only render that helper's answer.

**Tech Stack:**

- FastAPI, Pydantic, SQLAlchemy and Alembic on Postgres 18
- Svelte 5 with Vitest (`npx vp test`)
- Kotlin and Compose with JUnit
- SwiftUI with XCTest

**Spec:** [docs/superpowers/specs/2026-11-14-senior-equipment-design.md](../specs/2026-11-14-senior-equipment-design.md)

## Global Constraints

- The values are exactly `"smartphone"`, `"watch"` and `"home_node"`. `null` means not stated and `[]` means none.
- Lists are stored and returned de-duplicated, in the canonical order `smartphone, watch, home_node`.
- `"watch"` or `"home_node"` without `"smartphone"` is 422. `"smartphone"` with a landline senior number is 422. Both are checked only when the body carries a non-null `equipment`.
- `PUT /seniors/{id}` with `equipment` missing or `null` keeps the stored value. `POST /seniors` with it missing or `null` stores `null`.
- Additive only (ADR-001 §2.3): the column is nullable, and the new response fields are optional.
- User-facing copy is Romanian and exact:
  - section title „Echipamente”
  - boxes „Telefon cu aplicația EchoCare”, „Ceas”, „Senzor din casă”
  - legacy line „Nespecificat”
  - warnings „Ceas înregistrat, nu a trimis date”, „Senzor din casă înregistrat, nu a trimis date”, „Pacientul nu a deschis aplicația”
- **The display rule** is the same in all three clients:
  - `showsWatch = equipment == null || "watch" in equipment`
  - Warnings are empty when `equipment == null`, or when `enrollment_state` is not `accepted` or `active`, or when the viewer is the senior. Otherwise they come in this order:
    1. watch warning: `"watch" in equipment && watch_state == null`
    2. node warning: `"home_node" in equipment`
    3. app warning: `"smartphone" in equipment && app_signed_in == false`. A `null` from an older API shows no app warning.
- Warnings use the existing yellow (`galben`) device-warning tone. They push nothing and change no code.
- Cite spec IDs in new comments: UC-01, UC-13, `04 §1`, `04 §2`, design 2026-11-14.

## Review Focus

1. **An old APK edits a senior.** A `PUT` without `equipment`, or with `"equipment": null`, must keep `["smartphone", "watch"]`. This is pinned in Task 1.
2. **A senior registered before this change** (`equipment` null) must look exactly as today in every client: watch panel shown, no warnings. This is pinned in the helper tests of Tasks 3–5.
3. **A declared watch that starts reporting.** Once `watch_state` is `"ok"`, the watch warning disappears and the normal panel shows. Pinned in Tasks 3–5.
4. **A messy list,** such as `["watch", "smartphone", "watch"]` or `["tablet"]`. The first is de-duplicated and ordered, the second is 422. Pinned in Task 1.
5. **A number changed to a landline.** With `["smartphone"]` in the body it is 422. Without `equipment` the change is accepted and the stored list is kept. Pinned in Task 1.

---

### Task 1: Backend — the `equipment` field, its rules and the PUT keep rule

**Files:**
- Modify: `backend/app/seniors/models.py`. Add to `Senior`, after `call_window`: `equipment: Mapped[list[str] | None] = mapped_column(ARRAY(String(20)))`, with a one-line comment citing design 2026-11-14.
- Create: `backend/alembic/versions/<rev>_seniors_equipment.py`. Generate it in Compose (`docker compose exec api alembic revision --autogenerate -m "seniors equipment"`), keep only the `add_column` and `drop_column`, and write a docstring in the style of `e1a5b7c3d904_seniors_enrollment_times.py`.
- Modify: `backend/app/seniors/schemas.py`: `SeniorForm` and `SeniorView`.
- Test: `backend/tests/seniors/test_seniors.py`.
- Docs: in `docs/specs/echocare/05-data-model.md`, add `string[] equipment "smartphone, watch, home_node; null = not stated"` to the `SENIOR` entity, plus a sentence in the notes. In `docs/specs/echocare/04-interfaces.md` §2, add the field to the "Save senior draft" row: what it means, the two 422 rules, and the keep-on-missing-or-null rule.

**Interfaces:**
- Produces, in `app/seniors/schemas.py`:
  - `Equipment = Literal["smartphone", "watch", "home_node"]`
  - `EQUIPMENT_ORDER: tuple[str, ...] = ("smartphone", "watch", "home_node")`
  - `SeniorForm.equipment: list[Equipment] | None = None`
  - `SeniorView.equipment: list[str] | None = None`
- `SeniorForm.columns()` leaves out `equipment` when it is `None`. `service.edit` then keeps the column, and `register` leaves it `NULL`. `senior_view` already copies every `SeniorView` field from the row, so no change is needed there.

- [ ] **Step 1: Write the failing tests** in `test_seniors.py`, using the existing `register`, `signed_in`, `MARIA` and `staff` helpers:

```python
async def test_equipment_round_trips_ordered_and_deduplicated(client, staff):
    s = await register(client, {**MARIA, "equipment": ["watch", "smartphone", "watch"]})
    assert s["equipment"] == ["smartphone", "watch"]

async def test_equipment_not_sent_is_not_stated(client, staff):
    assert (await register(client))["equipment"] is None

async def test_empty_equipment_is_none_declared(client, staff):
    assert (await register(client, {**MARIA, "equipment": []}))["equipment"] == []

@pytest.mark.parametrize("equipment", [["watch"], ["home_node"], ["tablet"]])
async def test_equipment_refused(client, staff, equipment):
    r = await client.post("/api/seniors", json={**MARIA, "equipment": equipment},
                          headers=signed_in(MEDIC))
    assert r.status_code == 422

async def test_smartphone_needs_a_mobile(client, staff):
    body = {**MARIA, "phone": "0256 123 456", "equipment": ["smartphone"]}
    r = await client.post("/api/seniors", json=body, headers=signed_in(MEDIC))
    assert r.status_code == 422

@pytest.mark.parametrize("sent", [{}, {"equipment": None}])
async def test_put_without_equipment_keeps_it(client, staff, sent):
    s = await register(client, {**MARIA, "equipment": ["smartphone", "watch"]})
    r = await client.put(f"/api/seniors/{s['id']}", json={**MARIA, **sent},
                         headers=signed_in(MEDIC))
    assert r.status_code == 200, r.text
    assert r.json()["equipment"] == ["smartphone", "watch"]

async def test_put_replaces_equipment(client, staff):
    s = await register(client, {**MARIA, "equipment": ["smartphone", "watch"]})
    r = await client.put(f"/api/seniors/{s['id']}", json={**MARIA, "equipment": []},
                         headers=signed_in(MEDIC))
    assert r.json()["equipment"] == []

async def test_landline_edit_without_equipment_keeps_the_list(client, staff):
    s = await register(client, {**MARIA, "equipment": ["smartphone"]})
    r = await client.put(f"/api/seniors/{s['id']}",
                         json={**MARIA, "phone": "0256 123 456"}, headers=signed_in(MEDIC))
    assert r.status_code == 200, r.text
    assert r.json()["equipment"] == ["smartphone"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `cd backend && uv run pytest tests/seniors/test_seniors.py -k equipment -v`
Expected: FAIL. The responses have no `equipment` key, and the 422 cases pass validation.

- [ ] **Step 3: Implement the column, the migration and the schema fields.** On `SeniorForm`:
  - Add a `field_validator("equipment")` that returns `[e for e in EQUIPMENT_ORDER if e in value]` (or `None`).
  - Add a `model_validator(mode="after")` that raises `ValueError` for each of the two rules. For the mobile check, use `is_mobile(self.phone)` after the `e164` validator has run.
  - Change `columns()` so `model_dump` excludes `equipment` when it is `None`.

  Add `equipment` to `SeniorView` next to `call_window`. Apply the migration locally: `docker compose exec api alembic upgrade head`.

- [ ] **Step 4: Run the tests and see them pass**

Run: `cd backend && uv run pytest tests/seniors -v`
Expected: PASS, with no existing seniors test broken.

- [ ] **Step 5: Run the backend checks**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/seniors backend/alembic/versions backend/tests/seniors docs/specs/echocare/04-interfaces.md docs/specs/echocare/05-data-model.md
git commit -m "backend: seniors.equipment, declared at registration (design 2026-11-14)"
```

---

### Task 2: Backend — `app_signed_in`, the mock data and the use cases

**Files:**
- Modify: `backend/app/seniors/schemas.py`, `SeniorView`.
- Modify: `backend/app/seniors/service.py`, a new function next to `watch_state` (around line 814).
- Modify: `backend/app/seniors/router.py`, the `GET /seniors/{senior_id}` handler at the line that sets `view.watch_state` (around line 84).
- Modify: `backend/scripts/seed.py`, giving the mock seniors equipment.
- Test: `backend/tests/seniors/test_seniors.py`.
- Docs:
  - `04-interfaces.md` §1: the `GET /seniors/{id}` answer gains `equipment` and `app_signed_in`, with who sees the latter.
  - `02-use-cases.md` UC-01: a new step after step 3, on equipment, with the smartphone meaning from the design.
  - `02-use-cases.md` UC-13: a new numbered line for the never-reported warnings, with their states and viewers.

**Interfaces:**
- Consumes: `SeniorView.equipment` from Task 1.
- Produces:
  - `SeniorView.app_signed_in: bool | None = None`, set only by `GET /seniors/{id}`, as `call_in_progress` is.
  - `async def app_signed_in(session: AsyncSession, caller: Caller, senior: Senior) -> bool | None` in `service.py`. It returns `None` when `not sees_watch(caller, senior.id, senior.medic_id)`. Otherwise it returns whether a `User` holding a `Grant(role=Role.senior, senior_id=senior.id)` has `firebase_uid IS NOT NULL`, and `False` when there is no such grant.
- Add `"app_signed_in"` to the excluded names in `senior_view`, so it isn't read off the row.

- [ ] **Step 1: Write the failing tests**

```python
async def test_app_signed_in_after_the_senior_signs_in(client, staff):
    s = await register(client)
    page = (await client.get(f"/api/seniors/{s['id']}", headers=signed_in(MEDIC))).json()
    assert page["app_signed_in"] is False
    await client.get("/api/me", headers=signed_in(SENIOR))  # first sign-in sets firebase_uid
    page = (await client.get(f"/api/seniors/{s['id']}", headers=signed_in(MEDIC))).json()
    assert page["app_signed_in"] is True

async def test_app_signed_in_is_false_for_a_landline(client, staff):
    s = await register(client, {**MARIA, "phone": "0256 123 456"})
    page = (await client.get(f"/api/seniors/{s['id']}", headers=signed_in(MEDIC))).json()
    assert page["app_signed_in"] is False
```

If `GET /api/me` isn't how the fake token signs in, use whichever authenticated request `tests/auth` uses to attach `firebase_uid`.

- [ ] **Step 2: Run them and see them fail**

Run: `cd backend && uv run pytest tests/seniors/test_seniors.py -k app_signed_in -v`
Expected: FAIL with `KeyError: 'app_signed_in'`.

- [ ] **Step 3: Implement `app_signed_in`** and set `view.app_signed_in` in the GET handler, next to `view.watch_state`. Use one `select(User.firebase_uid.is_not(None))` joined to `Grant`, and `scalar()` with `False` as the fallback.

- [ ] **Step 4: Run them and see them pass**

Run: `cd backend && uv run pytest tests/seniors -v`
Expected: PASS.

- [ ] **Step 5: Seed a mix of equipment** in `seed.py`, so each case can be seen locally:
  - maria: `["smartphone", "watch"]`, which reports.
  - ion: `[]`, since he is on a landline and has no watch.
  - elena: `["smartphone", "watch"]`.
  - gheorghe: `["smartphone", "watch", "home_node"]`, which gives the node warning.
  - One active seeded senior: `["smartphone", "watch"]` with no `h.watch(...)`, which gives the watch warning.

  Pass `equipment=` wherever the seed builds `Senior(...)`.

Run: `cd backend && uv run python scripts/seed.py --reset`
Expected: completes with no error.

- [ ] **Step 6: Run the backend checks** as in Task 1, Step 5. Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add backend docs/specs/echocare
git commit -m "backend: app_signed_in on the senior page, seeded equipment (UC-01, UC-13)"
```

---

### Task 3: Dashboard — DAS shows only the declared devices

**Files:**
- Create: `dashboard/src/utils/equipment.ts`
- Test: `dashboard/src/utils/equipment.test.ts`
- Modify: `dashboard/src/services/api.ts`. In `SeniorView` (line 333), add `equipment?: string[] | null; app_signed_in?: boolean | null;`.
- Modify: `dashboard/src/features/seniors/SeniorDetails.svelte` (around line 390). Render `<WatchHealth>` only when `showsWatch(s)` and the watch warning is absent; otherwise its „Ceasul nu a trimis încă date.” would repeat the warning. Render each warning from `deviceWarnings(s)` as a chip with `TONE_CHIP.galben`, above it, with the watch `Icon` for the watch warning.

**Interfaces:**
- Produces:
  - `export function showsWatch(s: Pick<SeniorView, "equipment">): boolean`
  - `export function deviceWarnings(s: Pick<SeniorView, "equipment" | "watch_state" | "app_signed_in" | "enrollment_state">): string[]`. It returns the exact Romanian warning strings in the Global Constraints order. DAS is never the senior, so there is no viewer parameter.

- [ ] **Step 1: Write the failing tests** (Vitest, in the style of `utils/incidents.test.ts`):

```ts
const base = { equipment: ["smartphone", "watch"], watch_state: null,
               app_signed_in: false, enrollment_state: "active" };
it("hides the watch only when declared without one", () => {
  expect(showsWatch({ equipment: null })).toBe(true);
  expect(showsWatch({ equipment: [] })).toBe(false);
  expect(showsWatch({ equipment: ["smartphone"] })).toBe(false);
});
it("warns about a declared watch with no data and an unopened app", () => {
  expect(deviceWarnings(base)).toEqual([
    "Ceas înregistrat, nu a trimis date", "Pacientul nu a deschis aplicația"]);
});
it("stops warning once the watch reports and the app is opened", () => {
  expect(deviceWarnings({ ...base, watch_state: "ok", app_signed_in: true })).toEqual([]);
});
it("always warns about a declared home node", () => {
  expect(deviceWarnings({ ...base, equipment: ["smartphone", "home_node"], app_signed_in: true }))
    .toEqual(["Senzor din casă înregistrat, nu a trimis date"]);
});
it("is silent for a senior not stated, not yet accepted, or an older API", () => {
  expect(deviceWarnings({ ...base, equipment: null })).toEqual([]);
  expect(deviceWarnings({ ...base, enrollment_state: "submitted" })).toEqual([]);
  expect(deviceWarnings({ ...base, watch_state: "ok", app_signed_in: null })).toEqual([]);
});
```

- [ ] **Step 2: Run them and see them fail**

Run: `cd dashboard && npx vp test src/utils/equipment.test.ts`
Expected: FAIL, because the module isn't found.

- [ ] **Step 3: Implement `equipment.ts`**, then wire it into `SeniorDetails.svelte`. `WatchHealth.svelte` itself doesn't change.

- [ ] **Step 4: Run the tests and checks**

Run: `cd dashboard && npx vp test && npm run check`
Expected: all pass.

- [ ] **Step 5: Look at it.** Start the stack (`docker compose up --watch`), seed it, and open each seeded senior at http://localhost:5173. Expected:
  - maria: the watch panel.
  - ion: no watch panel and no warnings.
  - gheorghe: the node warning.
  - the senior with no check-in: the watch warning.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src
git commit -m "dashboard: watch panel and device warnings follow the declared equipment"
```

---

### Task 4: Android — the form's „Echipamente” and the device chips

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/Api.kt`:
  - `SeniorForm` (line 134) gains `val equipment: List<String>? = null`.
  - `SeniorPage` (line 55) gains `val equipment: List<String>? = null` and `@SerialName("app_signed_in") val appSignedIn: Boolean? = null`.
- Modify: `android/app/src/main/java/ro/echocare/enroll/Form.kt`:
  - `bodyOf(values: Map<Field, String>, equipment: Set<String>?)` passes `equipment?.let(::equipmentOf)`.
  - Add `fun equipmentOf(ticked: Set<String>): List<String>`: add `"smartphone"` when `"watch"` or `"home_node"` is ticked, then return the list in canonical order.
- Modify: the enroll screen and `EnrollViewModel.kt`. Hold `equipment: Set<String>?` in the form state:
  - `emptySet()` for a new registration.
  - The saved list for an edit, or `null` when it was `null`. Ticking any box turns `null` into a set.
  - Render the „Echipamente” section after the caregivers, showing „Nespecificat” while the value is `null`.
  - The phone box is checked and disabled while Ceas or Senzor is ticked, and disabled for a landline number (use the form's existing landline detection).
- Modify: `android/app/src/main/java/ro/echocare/home/Calls.kt`:
  - Add `fun showsWatch(senior: SeniorPage): Boolean` and `fun deviceWarnings(senior: SeniorPage, forSenior: Boolean): List<Int>`. The second returns string resource ids, following the Global Constraints rule; `forSenior = true` returns empty.
  - In `home/SeniorScreen.kt` (around line 385), guard the watch chip with `showsWatch` and render each warning as a `Tone.Galben` chip. Pass `forSenior = true` from the senior's own page and from step 4 of the registration form.
- Modify: `android/app/src/main/res/values/strings.xml`, adding the Romanian strings from the Global Constraints.
- Test: `android/app/src/test/java/ro/echocare/enroll/FormTest.kt` and a new `android/app/src/test/java/ro/echocare/home/DevicesTest.kt`.

**Interfaces:**
- Consumes: the API fields from Tasks 1–2.
- Produces: `equipmentOf`, `showsWatch` and `deviceWarnings`, as above.

- [ ] **Step 1: Write the failing tests**
  - `FormTest`:
    - `equipmentOf(setOf("watch")) == listOf("smartphone", "watch")`
    - `equipmentOf(emptySet()) == emptyList()`
    - `bodyOf(values, null).equipment == null`
  - `DevicesTest`: the same five cases as Task 3's tests, written against `SeniorPage` and `R.string` ids, plus `deviceWarnings(page, forSenior = true).isEmpty()` for a page that would otherwise warn.

- [ ] **Step 2: Run them and see them fail**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests '*FormTest' --tests '*DevicesTest'`
Expected: FAIL, because the helpers don't compile yet.

- [ ] **Step 3: Implement the API fields, the helpers, the form section and the chips.**

- [ ] **Step 4: Run the Android checks**

Run: `cd android && ./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 5: Commit**

```bash
git add android/app/src
git commit -m "android: equipment on the registration form, device warnings (UC-01, UC-13)"
```

---

### Task 5: iOS — the same, in SwiftUI

**Files:**
- Modify: `ios/EchoCare/Api/Api.swift`:
  - `SeniorForm` (line 244) gains `var equipment: [String]?`, with its `CodingKeys` entry.
  - `SeniorPage` (line 75) gains `var equipment: [String]?` and `var appSignedIn: Bool?`, decoded with `decodeIfPresent`, and the memberwise init gains defaulted parameters.
- Modify: `ios/EchoCare/Enroll/Form.swift` (`SeniorForm(` at line 165), `EnrollModel.swift` and `EnrollView.swift`. These mirror Task 4's form behaviour, with a free function `equipmentOf(_ ticked: Set<String>) -> [String]`.
- Modify: `ios/EchoCare/Home/Calls.swift`, next to `watchChip` (line 55). Add `func showsWatch(_ senior: SeniorPage) -> Bool` and `func deviceWarnings(_ senior: SeniorPage, forSenior: Bool) -> [String]`, which returns `Localizable.xcstrings` keys. Use them in `Home/SeniorView.swift` around line 110, with `forSenior` set as in Task 4.
- Modify: `ios/EchoCare/Localizable.xcstrings`, adding the Romanian strings. This file already has uncommitted local changes, so add to it without dropping them.
- Test: `ios/EchoCareTests/FormTests.swift` and `ios/EchoCareTests/CallsTests.swift`.

**Interfaces:**
- Consumes: the API fields from Tasks 1–2.
- Produces: `equipmentOf`, `showsWatch` and `deviceWarnings`, with Task 4's semantics.

- [ ] **Step 1: Write the failing tests**: Task 4's cases as XCTest, in `FormTests` and `CallsTests`.

- [ ] **Step 2: Run them and see them fail**

Run: `xcodebuild test -project ios/EchoCare.xcodeproj -scheme EchoCare -destination 'platform=iOS Simulator,name=iPhone 17'`
Expected: a build failure, because the helpers don't exist yet.

- [ ] **Step 3: Implement the API fields, the helpers, the form section and the chips.**

- [ ] **Step 4: Run the iOS checks**

Run the same `xcodebuild test` command, then `swift format lint --strict --parallel --recursive --configuration ios/.swift-format ios/EchoCare ios/EchoCareWatch ios/EchoCareTests ios/Shared`.
Expected: TEST SUCCEEDED, and lint is clean.

- [ ] **Step 5: Commit**

```bash
git add ios/EchoCare/Api ios/EchoCare/Enroll ios/EchoCare/Home ios/EchoCare/Localizable.xcstrings ios/EchoCareTests
git commit -m "ios: equipment on the registration form, device warnings (UC-01, UC-13)"
```

---

### Task 6: End-to-end check

- [ ] **Step 1:** With the stack up and seeded, register a new senior from the Android emulator, ticking only Ceas. Expected: the phone box ticks itself and locks.
- [ ] **Step 2:** Accept the senior on the dashboard. Expected: their page shows „Ceas înregistrat, nu a trimis date” and „Pacientul nu a deschis aplicația”, and no watch panel.
- [ ] **Step 3:** Run the hooks without committing: `lefthook run pre-commit && lefthook run pre-push`. Expected: all green.
