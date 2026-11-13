# Medic Home and Profile Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the medic's two-tile home with a to-do list sorted by importance, and replace the ⋮ menu with a profile page that switches role in one tap.

**Architecture:** The backend adds one optional field, `medical_record_state`, to `GET /seniors` rows, composed in the seniors router from a new `medical` service read (seniors may not import medical, ADR-005). Android derives the tasks from the rows in plain Kotlin beside `Panel.kt`, tested on the JVM. The profile page is a new nav destination opened from the initials square, which replaces the ⋮ menu in every top bar.

**Tech Stack:** FastAPI, SQLAlchemy, pytest (backend); Kotlin, Jetpack Compose, Navigation Compose, JUnit 4 (Android).

**Spec:** `docs/superpowers/specs/2026-11-13-medic-home-and-profile-design.md`

## Global Constraints

- Work on a branch, not `main` (`git switch -c medic-home-tasks`). Commit with the hooks on; never `--no-verify`.
- API changes only add: `medical_record_state` is optional and defaults to null (ADR-001 §2.3).
- Contract changes move together: `docs/specs/echocare/04-interfaces.md`, the backend and Android in this one branch. The dashboard ignores the field and does not change.
- Android decodes `medical_record_state` as `String?`. A value this build does not know produces no task and no crash.
- User-facing text is Romanian, using the formal address the app already uses („Alegeți rolul”). Code and comments in English, citing spec IDs.
- Backend checks: from `backend/`, `uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`. Tests use `echocare_test` (Postgres from `docker compose up db`).
- Android checks: from `android/`, `./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug`.

## Review Focus

1. **One senior, two tasks** (a profile in `review` and `wrong_number`): one row for that senior, the more important task, so the list has no duplicate keys. Test in Task 2.
2. **A medical state this build does not know, or a refused or withdrawn senior with a profile in review:** no task. Test in Task 2.
3. **The same senior read by DAS or a caregiver:** `medical_record_state` is null even when a record exists. Test in Task 1.
4. **A draft or welcome-call problem with no timestamp:** it still appears, after the ones that have one. Test in Task 2.
5. **A person with one role opening the profile:** their role shows alone and tapping it does nothing; tapping the current role of a multi-role person also does nothing. Manual check in Task 4.

---

### Task 1: `medical_record_state` on `GET /seniors` rows

**Files:**
- Modify: `backend/app/seniors/schemas.py` (`SeniorSummary`, after `watch_state`)
- Modify: `backend/app/medical/service.py` (new function)
- Modify: `backend/app/seniors/router.py:56-63` (`list_seniors`)
- Modify: `docs/specs/echocare/04-interfaces.md:25` (the `GET /seniors` row)
- Test: `backend/tests/medical/test_api.py`

**Interfaces:**
- Produces: JSON field `medical_record_state` on every `GET /seniors` row: `"pending" | "review" | "confirmed" | "failed" | null`. Task 2 reads it.

- [ ] **Step 1: Write the failing tests** in `backend/tests/medical/test_api.py`, reusing its `medic`, `das`, `active` fixtures and `seed` helper:

```python
async def seniors_rows(client, token, role=None):
    r = await client.get(
        "/api/seniors", params={"role": role} if role else None, headers=signed_in(token)
    )
    assert r.status_code == 200
    return {row["id"]: row for row in r.json()}


async def test_the_registering_medic_sees_the_record_state_on_the_row(client, db, active):
    await seed(db, active, MedicalRecordState.review)
    rows = await seniors_rows(client, MEDIC, "medic")
    assert rows[str(active.id)]["medical_record_state"] == "review"


async def test_no_record_is_null_on_the_row(client, active):
    rows = await seniors_rows(client, MEDIC, "medic")
    assert rows[str(active.id)]["medical_record_state"] is None


async def test_das_rows_carry_no_record_state(client, db, das, active):
    """01 §6: the record is the registering medic's; the row says nothing to DAS."""
    await seed(db, active, MedicalRecordState.confirmed)
    rows = await seniors_rows(client, DAS, "das")
    assert rows[str(active.id)]["medical_record_state"] is None
```

Add a caregiver case the same way if the file has a caregiver fixture; otherwise add a `caregiver` fixture granting a new number `Role.caregiver` on `active` (see `tests/seniors/test_check_ins.py` for how grants are added) and assert null.

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && uv run pytest tests/medical/test_api.py -k "row" -v`
Expected: FAIL with `KeyError: 'medical_record_state'`.

- [ ] **Step 3: Add the field** `medical_record_state: str | None = None` to `SeniorSummary`, with a comment: for the senior's registering medic only, null for anyone else and when no record is attached (04 §1, design 2026-11-13); a plain string because `seniors` sits below `medical` and may not import its enum (ADR-005).

- [ ] **Step 4: Implement `async def record_states(session: AsyncSession, caller: Caller) -> dict[uuid.UUID, MedicalRecordState]`** in `app/medical/service.py`: empty when `Role.medic not in caller.roles`; otherwise `MedicalRecord.senior_id, MedicalRecord.state` joined to `Senior` where `Senior.medic_id == caller.user.id`. One query.

- [ ] **Step 5: Compose it in `list_seniors`**: read the summaries, read `record_states(session, caller)`, set each row's `medical_record_state = states.get(row.id)`. Comment that the router composes them because `seniors` can't import `medical` (ADR-005), as `get_senior` does for `call_in_progress`.

- [ ] **Step 6: Run the tests and the backend checks**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
Expected: all pass.

- [ ] **Step 7: Update the contract.** In `04-interfaces.md` line 25, after the `watch_state` sentence, add: „The medical record's state as `medical_record_state` (`pending`, `review`, `confirmed`, `failed`), for the senior's registering medic only, null for anyone else and when no record is attached (design 2026-11-13); the submit, accept and consent-withdrawn answers leave it null.”

- [ ] **Step 8: Commit**

```bash
git add backend/app/seniors/schemas.py backend/app/seniors/router.py backend/app/medical/service.py backend/tests/medical/test_api.py docs/specs/echocare/04-interfaces.md
git commit -m "backend: medical_record_state on GET /seniors rows, for the registering medic (medic home)"
```

---

### Task 2: Medic tasks derived from the rows

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/Api.kt:30-47` (`SeniorRow`)
- Create: `android/app/src/main/java/ro/echocare/home/Tasks.kt`
- Test: `android/app/src/test/java/ro/echocare/home/TasksTest.kt` (create)

**Interfaces:**
- Consumes: `medical_record_state` from Task 1.
- Produces (used by Task 3):
  - `SeniorRow.medicalRecordState: String? = null`, `@SerialName("medical_record_state")`
  - `enum class TaskKind { Confirm, AnalysisFailed, WrongNumber, Unreachable, Draft }`, declared in this order, which is the order of importance
  - `data class MedicTask(val row: SeniorRow, val kind: TaskKind)`
  - `fun tasksOf(rows: List<SeniorRow>): List<MedicTask>`

**Rules for `tasksOf`** (the design doc's order, plus the Review Focus):
- `kindOf(row)`: `Confirm` when `medicalRecordState == "review"`, `AnalysisFailed` when `"failed"`, both only when the state is not `refused`, `withdrawn` or unknown to `STATE_LABELS`. Otherwise `WrongNumber` for `wrong_number`, `Unreachable` for `unreachable`, `Draft` for `draft`, else no task. A row with a medical task and a welcome-call problem yields only the medical one (one task per senior).
- Order: by `kind` ordinal; within a kind, oldest first by `createdAt` for `Draft`, by `acceptedAt` for `WrongNumber` and `Unreachable`, null times last; the API's order otherwise (stable sort). Use `instantOf` from `Panel.kt`.

- [ ] **Step 1: Write the failing tests** in `TasksTest.kt`, with a `row(id, state, medical = null, createdAt = null, acceptedAt = null)` helper like `PanelTest`'s:

```kotlin
@Test fun ordersByImportance() {
    val rows = listOf(
        row("d", "draft"), row("u", "unreachable"), row("w", "wrong_number"),
        row("f", "active", medical = "failed"), row("c", "active", medical = "review")
    )
    assertEquals(listOf("c", "f", "w", "u", "d"), tasksOf(rows).map { it.row.id })
}

@Test fun oneTaskPerSeniorTheMostImportant() {
    val tasks = tasksOf(listOf(row("a", "wrong_number", medical = "review")))
    assertEquals(listOf(MedicTask(tasks[0].row, TaskKind.Confirm)), tasks)
}

@Test fun noTaskForUnknownOrSettledValues() {
    val rows = listOf(
        row("x", "active", medical = "archived"), row("y", "withdrawn", medical = "review"),
        row("z", "refused", medical = "failed"), row("q", "someday"),
        row("g", "active", medical = "confirmed"), row("s", "submitted")
    )
    assertEquals(emptyList<MedicTask>(), tasksOf(rows))
}

@Test fun oldestFirstWithinAKindNullTimesLast() {
    val rows = listOf(
        row("new", "draft", createdAt = "2026-11-12T10:00:00Z"),
        row("none", "draft"),
        row("old", "draft", createdAt = "2026-11-10T10:00:00Z")
    )
    assertEquals(listOf("old", "new", "none"), tasksOf(rows).map { it.row.id })
}
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "ro.echocare.home.TasksTest"`
Expected: FAIL, unresolved `tasksOf`.

- [ ] **Step 3: Add `medicalRecordState` to `SeniorRow`**, with a comment: the medical record's state for the registering medic, a string for a later server's value (design 2026-11-13, ADR-001 §2.3).

- [ ] **Step 4: Implement `Tasks.kt`** with the interfaces and rules above.

- [ ] **Step 5: Run the tests**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "ro.echocare.home.*"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add android/app/src/main/java/ro/echocare/Api.kt android/app/src/main/java/ro/echocare/home/Tasks.kt android/app/src/test/java/ro/echocare/home/TasksTest.kt
git commit -m "android: the medic's tasks from the patient rows, by importance (medic home)"
```

---

### Task 3: The medic home as a to-do list

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/home/MedicHome.kt` (rewrite `MedicHomeScreen`, drop `Tile`)
- Modify: `android/app/src/main/java/ro/echocare/home/Panel.kt:63-69` (`Counts`, `countsOf`) and its test at `android/app/src/test/java/ro/echocare/home/PanelTest.kt:114`
- Delete: `android/app/src/main/java/ro/echocare/home/Register.kt`
- Modify: `android/app/src/main/java/ro/echocare/home/Routes.kt` (drop `RegisterRoute`, update `MedicHomeRoute`'s comment)
- Modify: `android/app/src/main/java/ro/echocare/home/HomeNav.kt` (drop the `RegisterRoute` destination; wire the new callbacks)
- Modify: `android/app/src/main/java/ro/echocare/home/Monitor.kt:58,75` (`onRegister` becomes `onNew`, label `R.string.new_patient`)
- Modify: `android/app/src/main/res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/home/RoutesTest.kt:43` (delete the `draftsNewestFirst` test with the function)

**Interfaces:**
- Consumes: `tasksOf`, `MedicTask`, `TaskKind` from Task 2.
- Changes: `data class Counts(val red: Int, val yellow: Int, val green: Int, val atDas: Int)` and `countsOf(rows)` (green = `active` with code `green`; atDas = state `submitted`). Update `PanelTest.kt:114` first to expect the new fields from its rows, see it fail, then change `Panel.kt`.
- Produces: `MedicHomeScreen(menu, onMonitor: () -> Unit, onNew: () -> Unit, onOpen: (String) -> Unit, onDraft: (String) -> Unit, onSessionEnd, sent, onSentShown, vm)`. In `HomeNav`: `onNew = { nav.navigate(EnrollRoute()) }`, `onOpen = { nav.navigate(SeniorRoute(it)) }`, `onDraft = { nav.navigate(EnrollRoute(it)) }`.

**Screen** (layout A from the mockups):
- Top bar: an `SnButton` „Pacient nou” (`R.string.new_patient`) in the `menu` slot, before `menu()`.
- Kept at the top: `NotificationsPrompt()` and the „Trimis la DAS.” banner.
- Strip: `Chip`s for red (`Tone.Rosu`), yellow (`Tone.Galben`), green (`Tone.Verde`) and at-DAS (`Tone.Link`), each only when above zero, then a `Kind.Link` button „Toți pacienții →” calling `onMonitor`. Wraps with `FlowRow`.
- `SectionLabel` „De făcut · N”, then one row per task: a 4dp bar in the kind's colour (Confirm, AnalysisFailed: `Palette.Link`; WrongNumber, Unreachable: `Palette.Galben`; Draft: `Palette.LineStrong`), the form of address and full name, the task line, and an outline button. Draft calls `onDraft(id)`, every other kind `onOpen(id)`. Rows look like `PatientCard` in `Monitor.kt`.
- Empty: `Message(„Totul e la zi”)` in place of the list.
- Width: one column, `widthIn(max = 720.dp)`, centred, on any screen.

**Strings** (add to `strings.xml`; remove `register`, `count_to_resolve`, `drafts_left` and `drafts` if lint reports them unused):

| name | text |
|---|---|
| `tasks_title` | De făcut · %d |
| `all_done` | Totul e la zi |
| `all_patients` | Toți pacienții → |
| `count_green` | Verzi: %d |
| `count_at_das` | La DAS: %d |
| `task_confirm` | Fișa medicală e analizată: confirmați întrebările |
| `task_failed` | Analiza fișei medicale a eșuat |
| `task_wrong_number` | Număr greșit la apelul de bun venit |
| `task_unreachable` | Nu răspunde la apelul de bun venit |
| `task_draft` | Înregistrare neterminată |
| `do_review` | Revizuiește |
| `do_open` | Deschide |
| `do_correct` | Corectează |
| `do_call_again` | Sună din nou |
| `do_continue` | Continuă |

- [ ] **Step 1: Delete `Register.kt`, `RegisterRoute` and the `draftsNewestFirst` test;** point Monitorizare's empty state at `onNew`.
- [ ] **Step 2: Add the strings.**
- [ ] **Step 3: Rewrite `MedicHomeScreen`** as above and wire it in `HomeNav`.
- [ ] **Step 4: Run the Android checks**

Run: `cd android && ./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug`
Expected: BUILD SUCCESSFUL, no new lint warnings.

- [ ] **Step 5: Check it on the tablet emulator** against the local stack seeded with `cd backend && uv run python scripts/seed.py`: sign in as a seeded medic, confirm tasks appear in the order of Task 2, each button opens the right page, „Toți pacienții →” opens Monitorizare, and a medic with no tasks sees „Totul e la zi”. Screenshot with `android screen capture`.

- [ ] **Step 6: Commit**

```bash
git add -A android/app/src
git commit -m "android: the medic home leads with tasks; Înregistrare folds into it (medic home)"
```

---

### Task 4: The profile page

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/auth/Screen.kt:25,33-38` (`Screen.Home`, `screenFor`)
- Modify: `android/app/src/main/java/ro/echocare/auth/AuthViewModel.kt:169-175` (`pickRole`; delete `switchRole`)
- Modify: `android/app/src/main/java/ro/echocare/MainActivity.kt:91-98` (pass `onPickRole`, `phone`)
- Modify: `android/app/src/main/java/ro/echocare/home/Routes.kt` (add `ProfileRoute`)
- Create: `android/app/src/main/java/ro/echocare/home/Profile.kt`
- Modify: `android/app/src/main/java/ro/echocare/home/Frame.kt:120,214-241` (move `SignedIn` into a public `ProfileButton`)
- Modify: `android/app/src/main/java/ro/echocare/home/HomeNav.kt` (delete `HomeMenu`/`MenuItem`; add the destination)
- Modify: `android/app/src/main/res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/auth/ScreenTest.kt`

**Interfaces:**
- Produces:
  - `Screen.Home(val role: String, val displayName: String, val roles: List<String>)` with `val canSwitch: Boolean get() = roles.size > 1`. `roles` is the distinct known roles in `ROLES` order, as `screenFor` already computes.
  - `data object ProfileRoute`
  - `@Composable fun ProfileButton(onClick: () -> Unit)` in `Frame.kt`: the initials square (and the name on wide screens) as one clickable with `Role.Button` and content description `R.string.profile`.
  - `@Composable fun ProfileScreen(home: Screen.Home, phone: String?, onBack: () -> Unit, onPickRole: (String) -> Unit, onSignOut: () -> Unit)` in `Profile.kt`.
  - `HomeNav(home, phone: String?, onPickRole: (String) -> Unit, onSignOut, onSessionEnd, opening, onOpened)`.

**Behaviour:**
- `TopBar` no longer draws `SignedIn` itself. `HomeNav`'s `menu` becomes `{ ProfileButton { nav.navigate(ProfileRoute) } }`, and `SeniorRoute`'s `menu = {}` becomes `menu`, so every top bar has it. `ProfileScreen` passes `menu = {}`.
- `ProfileScreen` uses `HomeScaffold(„Profil”, onBack)`. Initials (larger square), display name, `phone` in `Mono` when not null. Section „Rol”: one row per `home.roles` with `ROLE_LABELS` (move it from `MainActivity.kt` to `Screen.kt` so both use it) and the role's line; the current role marked with a `Chip(„Activ”, Tone.Link)` and not clickable; any other role clickable, calling `onPickRole(role)`. Section „Notificări”: „Alerte pe acest telefon” with `Chip(„Pornite”, Tone.Verde)` or `Chip(„Oprite”, Tone.Galben)` from `notificationsAllowed(context)`, re-read on resume as `NotificationsPrompt` does; when off, tapping it opens `Settings.ACTION_APP_NOTIFICATION_SETTINGS`. Last, „Ieșire” as a full-width outline button calling `onSignOut`.
- `MainActivity` passes `onPickRole = vm::pickRole` and `phone = auth.currentUser?.phoneNumber`. `pickRole` builds `Screen.Home(role, me.displayName, roles)`; the new role's graph starts at its home because `HomeNav` is keyed on `home.role`.

**Strings:** add `profile` „Profil”, `profile_role` „Rol”, `role_active` „Activ”, `role_line_das` „Incidentele roșii”, `role_line_medic` „Sarcinile și pacienții dumneavoastră”, `role_line_caregiver` „Seniorii de care aveți grijă”, `role_line_senior` „Pagina dumneavoastră”, `notifications` „Notificări”, `notifications_device` „Alerte pe acest telefon”, `notifications_state_on` „Pornite”, `notifications_state_off` „Oprite”. Remove `change_role` and `menu`.

- [ ] **Step 1: Write the failing test** in `ScreenTest.kt`: update the existing `Screen.Home(...)` expectations to the new constructor, and add

```kotlin
@Test fun homeListsEveryKnownRoleInOrder() {
    val me = Me("Ana Pop", listOf(Grant("caregiver"), Grant("medic"), Grant("das"), Grant("pilot")))
    val home = screenFor(me, saved = "medic") as Screen.Home
    assertEquals(listOf("das", "medic", "caregiver"), home.roles)
    assertTrue(home.canSwitch)
}
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "ro.echocare.auth.ScreenTest"`
Expected: FAIL to compile, no parameter `roles`.

- [ ] **Step 3: Change `Screen.Home` and `screenFor`;** update `pickRole`, delete `switchRole`.
- [ ] **Step 4: Run the test**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "ro.echocare.auth.ScreenTest"`
Expected: PASS.

- [ ] **Step 5: Build `ProfileButton`, `ProfileRoute`, `ProfileScreen`, the strings, and the `HomeNav`/`MainActivity` wiring;** delete `HomeMenu` and `MenuItem`.
- [ ] **Step 6: Run the Android checks**

Run: `cd android && ./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 7: Check it on the emulator:** with a number holding several roles (grant one in the local DB, or use a seeded staff number), tap the initials, switch from medic to DAS and back, and confirm each lands on that role's home. With a one-role number, confirm the role shows alone and does nothing on tap. Confirm „Ieșire” signs out. Screenshot both.

- [ ] **Step 8: Commit**

```bash
git add -A android/app/src
git commit -m "android: a profile page from the initials switches role in one tap; the ⋮ menu goes (medic home)"
```
