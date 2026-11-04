# Medic Tablet Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The medic's tablet home (Monitorizare, Înregistrare), the patient panel ordered by need, „Sună din nou”, „Retragere consimțământ” and the optional signature, with the backend fields and endpoint they need (issue #54).

**Architecture:** Two branches, one component each (AGENTS.md "How changes ship"). The backend branch adds three nullable `seniors` columns, optional response fields, and `POST /seniors/{id}/welcome-call`, with the spec updated in the same commits. The Android branch, cut from the backend branch, puts the pure logic (grouping, actions, timeline, signature points) in JVM-tested Kotlin files and builds the screens on top.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest (backend); Kotlin, Jetpack Compose, Hilt, Retrofit, kotlinx.serialization, JUnit (Android).

**Spec:** [docs/superpowers/specs/2026-11-04-medic-tablet-panel-design.md](../specs/2026-11-04-medic-tablet-panel-design.md). Read it before any task; it says why.

## Global Constraints

- API changes only add: new response fields optional with default null; no rename, no drop (ADR-001 §2.3). The migration adds nullable columns only.
- Backend: `uv run ruff check .`, `uv run ruff format --check .`, `uv run lint-imports`, `uv run pytest` pass before each commit (lefthook runs them). `seniors` must not import `voice` (ADR-005); the router composes.
- Android: `./gradlew :app:testDebugUnitTest` and `./gradlew :app:lint` pass. Decode leniently: states, decisions, methods stay `String`, never a Kotlin `enum` decoded from JSON.
- User-facing text is Romanian, in `android/app/src/main/res/values/strings.xml`. Code and comments English, citing the spec by ID (`UC-04`, `04 §2`, `G7`).
- Look: `Palette`, `Tone`, `ui/Components.kt` (`SnButton`, `Chip`, `Banner`), no rounded corners, 2dp rules (07 spec).
- Signature version string: `v1-semnatura`. Text: „Vă vom suna în zilele cu vreme extremă sau când ceasul semnalează ceva neobișnuit. Ce spuneți în apel văd medicul de familie, familia și DAS. Puteți renunța oricând. Semnând mai jos, sunteți de acord.”
- Two-pane breakpoint: width ≥ 840.dp (`TWO_PANE_MIN`).
- Never push, merge or open a PR unless the user asks. Hooks stay on.

## Review Focus

1. **An older API without the new fields.** The app must decode rows and pages with no `created_at`, `watch_state`, `consent`, `signed_at` and show them without dates or chips, never crash. Test in Task 5.
2. **A double tap on „Sună din nou”.** One call queued, 200 both times, no error banner. Backend test in Task 4; the Android button is disabled while the command is in flight (Task 10).
3. **„Sună din nou” or „Retrage” on a senior whose state moved meanwhile** (DAS withdrew, the call already ended). The server says `wrong_state`; the app shows the refusal in a `Banner` and rereads, so the patient lands in their real group. Test in Task 10 (`commandOutcome`).
4. **A signature that is one tap, or very long.** A single-point stroke is sent as one point; more than 5,000 points are thinned to ≤ 5,000, keeping each stroke's first and last point. An empty pad keeps „Salvează semnătura” disabled. Tests in Task 11.
5. **Rotating the tablet or crossing the breakpoint** keeps the selected patient: on a phone the selection opens the patient page, back on the tablet it is still selected. Selection lives in `SavedStateHandle`. Covered by the manual check in Task 12.

---

## Branch setup

- [ ] Run from the repo root: `git fetch origin && git switch -c 54-medic-panel-backend origin/main`, then add the design doc and this plan: `git add docs/superpowers/specs/2026-11-04-medic-tablet-panel-design.md docs/superpowers/plans/2026-11-04-medic-tablet-panel.md && git commit -m "docs: medic tablet panel design and plan (#54)"`.

---

### Task 1: Enrollment timestamps

**Files:**
- Create: `backend/alembic/versions/e1a5b7c3d904_seniors_enrollment_times.py` (revision `e1a5b7c3d904`, down_revision `c7a4e2f95d18`)
- Modify: `backend/app/seniors/models.py` (`Senior`), `backend/app/seniors/service.py` (`move`, `submit`, `accept`, `enrollments_query`), `backend/app/seniors/schemas.py` (`SeniorSummary`, `SeniorView`)
- Modify: `docs/specs/echocare/05-data-model.md` §1 (`SENIOR` block: `datetime submitted_at`, `datetime accepted_at`, `uuid accepted_by FK`), `docs/specs/echocare/04-interfaces.md` §1 (`GET /seniors` and `GET /seniors/{id}`: `created_at`, `submitted_at`, `accepted_at`; `GET /enrollments`: "by `submitted_at`, then `created_at`, then `id`")
- Test: `backend/tests/seniors/test_enrollments.py`

**Interfaces:**
- Produces: `Senior.submitted_at: Mapped[datetime | None]`, `Senior.accepted_at: Mapped[datetime | None]`, `Senior.accepted_by: Mapped[uuid.UUID | None]` (FK `users.id`). `move(session, caller, senior, before: EnrollmentState | tuple[EnrollmentState, ...], after: EnrollmentState, *, values: dict[str, Any] | None = None) -> None`. `SeniorSummary` and `SeniorView` gain `created_at: datetime | None = None`, `submitted_at: datetime | None = None`, `accepted_at: datetime | None = None`.

- [ ] **Step 1: Write the failing tests** in `test_enrollments.py`:

```python
async def test_submit_and_accept_stamp_their_times(client, db, staff):
    maria = await register(client)
    before = datetime.now(UTC)
    row = (await submit(client, maria)).json()
    assert row["accepted_at"] is None
    assert timedelta(0) <= datetime.fromisoformat(row["submitted_at"]) - before < timedelta(seconds=5)
    row = (await accept(client, maria)).json()
    senior = await db.get(Senior, uuid.UUID(maria))
    await db.refresh(senior)
    assert senior.accepted_by == (await user_id(db, DAS))
    assert row["accepted_at"] is not None and row["created_at"] is not None

async def test_a_refused_move_stamps_nothing(client, db, staff):
    maria = await register(client)
    await submit(client, maria)
    first = (await client.get(f"/api/seniors/{maria}", headers=signed_in(MEDIC))).json()["submitted_at"]
    assert refusal(await submit(client, maria)) == ALREADY_DONE
    again = (await client.get(f"/api/seniors/{maria}", headers=signed_in(MEDIC))).json()["submitted_at"]
    assert again == first

async def test_enrollments_by_submit_time(client, db, staff):
    # registered first, submitted second: listed second
    early = await register(client)
    late = await register(client, {**MARIA, "phone": "0700 000 006"})
    await submit(client, late)
    await submit(client, early)
    assert [r["id"] for r in (await enrollments(client)).json()] == [late, early]
```

`user_id(db, phone)` is a small helper selecting `User.id` by `phone_e164`. Adjust `test_enrollments_oldest_first` if it now contradicts the new order.

- [ ] **Step 2: Run them.** `cd backend && uv run pytest tests/seniors/test_enrollments.py -v`. Expected: the three new tests FAIL (missing keys / wrong order).
- [ ] **Step 3: Implement.** Columns `DateTime(timezone=True)` nullable, `accepted_by` `ForeignKey("users.id")` nullable. Write the migration by hand in the style of `c7a4e2f95d18_calls_dialed_at.py` (three `op.add_column`, `downgrade` drops them). `move` puts `**(values or {})` into the same `.values(...)` and matches `enrollment_state.in_(before)` for a tuple. `submit` passes `values={"submitted_at": func.now()}`; `accept` passes `values={"accepted_at": func.now(), "accepted_by": caller.user.id}`; refresh those columns with `enrollment_state` after the commit. `enrollments_query` orders by `Senior.submitted_at.asc().nulls_last(), Senior.created_at, Senior.id`. `senior_summaries` and `senior_view` copy every model field by name already, so the new schema fields fill themselves.
- [ ] **Step 4: Run the whole suite.** `uv run pytest`. Expected: PASS (the migration runs in the session fixture).
- [ ] **Step 5: Update 04 §1 and 05 §1** as listed under Files.
- [ ] **Step 6: Commit.** `git add backend docs/specs && git commit -m "seniors: submitted_at, accepted_at, accepted_by; enrollments by submit time (#54, 04 §1, 05 §1)"`

---

### Task 2: The watch's state on the rows

**Files:**
- Modify: `backend/app/seniors/schemas.py` (`SeniorSummary`), `backend/app/seniors/service.py` (`senior_summaries`, `watch_state`)
- Modify: `docs/specs/echocare/04-interfaces.md` §1 `GET /seniors` (the watch state moves from "added with their work" to the listed fields, same rule as `GET /seniors/{id}`)
- Test: `backend/tests/seniors/test_check_ins.py`

**Interfaces:**
- Produces: `SeniorSummary.watch_state: WatchCondition | None = None`. `def sees_watch(caller: Caller, senior_id: uuid.UUID, medic_id: uuid.UUID) -> bool` in `seniors/service.py`, used by both `watch_state` and `senior_summaries`. Other answers that build a `SeniorSummary` (submit, accept, withdraw, enrollments) leave it null.

- [ ] **Step 1: Write the failing tests:** `test_the_rows_carry_the_watch_state_for_her_medic_and_caregiver` (after a check-in with `worn=False`, `GET /seniors?role=medic` as the registering medic and `?role=caregiver` as the caregiver both show `"watch_state": "not_worn"`), `test_das_rows_carry_no_watch_state` (DAS sees `None` for the same senior), `test_no_check_in_yet_is_null_on_the_row`. Use the fixtures the file already has.
- [ ] **Step 2: Run them.** `uv run pytest tests/seniors/test_check_ins.py -v`. Expected: FAIL (`KeyError: 'watch_state'`).
- [ ] **Step 3: Implement.** `senior_summaries` outer-joins `WatchState` on `senior_id`, adds `WatchState.state` to the columns, excludes `watch_state` from the copied names, and sets it only where `sees_watch(caller, senior.id, senior.medic_id)`.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Update 04 §1**, then commit: `git commit -am "seniors: the watch state on GET /seniors rows (#54, UC-12, 04 §1)"`

---

### Task 3: Consent state and the signature text

**Files:**
- Modify: `backend/app/seniors/schemas.py` (new `ConsentView`; `SeniorView`), `backend/app/seniors/service.py` (new `consent_fields`; `senior_view`), `backend/app/voice/dialogue.py` (constants)
- Modify: `docs/specs/echocare/04-interfaces.md` §1 `GET /seniors/{id}` (`consent`, `consent_given_at`, `signed_at` with the rules from the design's "Consent state on the senior"), §2 "Save signature" row (names `v1-semnatura` and quotes its text)
- Test: `backend/tests/seniors/test_consents.py`

**Interfaces:**
- Produces: `class ConsentView(BaseModel): decision: State; method: State; at: datetime`. `SeniorView` gains `consent: ConsentView | None = None`, `consent_given_at: datetime | None = None`, `signed_at: datetime | None = None`. `async def consent_fields(session: AsyncSession, senior_id: uuid.UUID) -> dict[str, Any]` returning those three keys. `SIGNATURE_CONSENT_VERSION = "v1-semnatura"` and `SIGNATURE_CONSENT_TEXT` (exact text in Global Constraints) in `voice/dialogue.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_signature_is_not_the_consent`: sign a `submitted` senior; the page has `consent is None`, `consent_given_at is None`, `signed_at` set.
  - `test_the_consent_is_the_latest_decision_off_the_call`: add `Consent(given, call)` then `Consent(given, signature)` rows; `consent == {"decision": "given", "method": "call", "at": ...}`.
  - `test_a_withdrawal_keeps_when_consent_was_given`: active senior with `Consent(given, app)` at T, then withdraw through the API; `consent["decision"] == "withdrawn"`, `consent["method"] == "medic"`, `consent_given_at` == T.
  - `test_a_refusal_is_the_consent`: `Consent(refused, call)` gives `consent["decision"] == "refused"` and `consent_given_at is None`.
  - `test_the_signature_text`: `SIGNATURE_CONSENT_VERSION == "v1-semnatura"` and `SIGNATURE_CONSENT_TEXT.endswith("Semnând mai jos, sunteți de acord.")`.
- [ ] **Step 2: Run them.** `uv run pytest tests/seniors/test_consents.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** `consent_fields` makes three scalar queries on `Consent` for the senior, ordered `at desc, id desc`: the latest with `method != signature`; the latest `given` with `method in (call, app)` (its `at`); the latest with `method == signature` (its `at`). `senior_view` adds `**await consent_fields(session, senior.id)` and excludes the three names from the copied fields.
- [ ] **Step 4: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 5: Update 04 §1 and §2**, then commit: `git commit -am "seniors: consent, consent_given_at, signed_at; the v1-semnatura text (#54, G7, 04 §1-2)"`

---

### Task 4: `POST /seniors/{id}/welcome-call`

**Files:**
- Modify: `backend/app/seniors/service.py` (new `call_again`), `backend/app/calls/service.py` (new `welcome_call_pending`), `backend/app/seniors/router.py` (new endpoint)
- Modify: `docs/specs/echocare/04-interfaces.md` §2 "Call again" row: effect "moves the senior to `accepted` and queues a welcome call (attempt 1, due now) in one step; the number is not checked; answers like submit; a repeat (already `accepted` with a welcome call queued or live) answers the same and queues nothing"; refused "any other state (`wrong_state`)". Drop "after a corrected number".
- Test: `backend/tests/seniors/test_welcome_call.py` (new)

**Interfaces:**
- Consumes: `move` with a tuple `before` (Task 1); `queue_welcome_call(session, senior_id)` (exists); `own_senior` (exists, locks the row).
- Produces: `async def call_again(session, caller, senior_id, *, then: Hook, pending: Callable[[AsyncSession, uuid.UUID], Awaitable[bool]]) -> SeniorSummary`. `async def welcome_call_pending(session: AsyncSession, senior_id: uuid.UUID) -> bool`: a `welcome` call for the senior in `queued`, `ringing` or `in_progress`. Route `POST /api/seniors/{senior_id}/welcome-call`, `require_roles(Role.medic)`, answers `SeniorSummary`.

- [ ] **Step 1: Write the failing tests** (reuse `register`/`submit`/`accept` helpers by importing them from `test_enrollments`, or copy them):
  - `test_call_again_from_unreachable` and `test_call_again_from_wrong_number` (parametrize): set the state in the db, POST; 200, `enrollment_state == "accepted"`, one new `welcome` call `queued`, `attempt == 1`, due within 1 s of now; `accepted_at` unchanged.
  - `test_call_again_with_the_same_number` (wrong_number, no edit): 200. No number check.
  - `test_a_repeat_answers_the_same`: POST twice; both 200, still one queued welcome call.
  - `test_accepted_without_a_pending_call_is_wrong_state`: `accepted`, no call; `WRONG_STATE`.
  - `test_other_states_are_wrong_state` parametrized over `draft`, `submitted`, `active`, `refused`, `withdrawn`: `WRONG_STATE`, no call queued.
  - `test_only_her_medic`: other medic `NOT_FOUND`, DAS `NOT_ALLOWED` (403 from `require_roles` for a DAS-only caller), caregiver 403.
  - `test_the_card_offers_it_again`: `unreachable` mobile senior with a senior grant; after POST, `GET /api/profile/mock-call` as the senior returns the welcome call (set up as `tests/calls/test_mock_calls.py` does).
  - `test_a_second_round_ends_unreachable_again`: after POST, end the queued call as not answered twice through the same step `tests/calls/test_ending.py::test_a_second_welcome_that_gets_nowhere_makes_the_senior_unreachable` uses; the senior is `unreachable`.
- [ ] **Step 2: Run them.** `uv run pytest tests/seniors/test_welcome_call.py -v`. Expected: FAIL (404 on the route).
- [ ] **Step 3: Implement `call_again`:** `own_senior` (locks); if `accepted` and `await pending(...)`: return the summary unchanged; if not `wrong_number`/`unreachable`: `refuse(409, "wrong_state")` with the module's log line; else `await then(session, senior.id)` then `move(session, caller, senior, (wrong_number, unreachable), accepted)`, which commits both. Docstring cites UC-04 and 04 §2.
- [ ] **Step 4: Run** `uv run pytest && uv run lint-imports && uv run ruff check . && uv run ruff format --check .` Expected: all PASS.
- [ ] **Step 5: Update 04 §2**, then commit: `git commit -am "seniors: POST /seniors/{id}/welcome-call, Sună din nou (#54, UC-04, 04 §2)"`

**Backend branch done.** Ask the user before pushing or opening its PR. Then: `git switch -c 54-medic-panel-android`.

---

### Task 5: Api.kt, labels and `editable`

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/Api.kt`, `android/app/src/main/java/ro/echocare/home/Routes.kt` (`editable`, `STATE_LABELS`, `STATE_TONES`), `android/app/src/main/res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/ApiTest.kt`, `android/app/src/test/java/ro/echocare/home/RoutesTest.kt`

**Interfaces:**
- Produces: `SeniorRow` gains `createdAt`, `submittedAt`, `acceptedAt`, `watchState: String?` (all `= null`, `@SerialName` snake_case). `SeniorPage` gains `createdAt`, `submittedAt`, `acceptedAt`, `consent: ConsentState? = null`, `consentGivenAt`, `signedAt`. `@Serializable data class ConsentState(val decision: String, val method: String, val at: String)`. `@Serializable data class SignatureForm(@SerialName("text_version") val textVersion: String, val strokes: List<List<List<Float>>>)`. On `EchoCareApi`: `@POST("seniors/{id}/welcome-call") suspend fun callAgain(@Path("id") id: String): SeniorRow`, `@POST("seniors/{id}/consent-withdrawn") suspend fun withdraw(@Path("id") id: String): SeniorRow`, `@POST("seniors/{id}/signature") suspend fun sign(@Path("id") id: String, @Body body: SignatureForm): Response<Unit>`, `@GET("calls/{id}/transcript") suspend fun transcript(@Path("id") id: String): IncidentCall` (the transcript is the incident page's call plus answers, which are ignored). **Delete `editable` from `Routes.kt`** and the `takeIf { editable(senior.state) }` in `SeniorScreen.kt`: editing is allowed in every state (04 §2, SE9), drafts open the form anyway, and `onEdit` stays null for everyone but the medic. Remove its cases from `RoutesTest`. `STATE_LABELS["withdrawn"] = R.string.state_withdrawn` („Retras”), tone `Tone.Muted`.

- [ ] **Step 1: Write the failing tests:** in `ApiTest`, `a row and a page from an older API decode` (JSON without any new key → all new fields null) and `a page with consent decodes` (`"consent": {"decision":"withdrawn","method":"medic","at":"…"}` and an unknown `"method":"robot"` both decode). In `RoutesTest`, `withdrawn has a label`.
- [ ] **Step 2: Run.** `cd android && ./gradlew :app:testDebugUnitTest --tests 'ro.echocare.ApiTest' --tests 'ro.echocare.home.RoutesTest'`. Expected: FAIL to compile.
- [ ] **Step 3: Implement** as listed. Fix the comment on `updateSenior` that says PUT refuses past `submitted` (04 §2, SE9 allow any state).
- [ ] **Step 4: Run** `./gradlew :app:testDebugUnitTest`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -am "android: the medic panel's fields and commands in Api.kt (#54, 04 §1-2)"`

---

### Task 6: The panel's logic

**Files:**
- Create: `android/app/src/main/java/ro/echocare/home/Panel.kt`
- Test: `android/app/src/test/java/ro/echocare/home/PanelTest.kt`

**Interfaces:**
- Produces:

```kotlin
enum class Group(@StringRes val title: Int) { Urgent, ToResolve, InProgress, Green, AtDas, Inactive }
fun groupOf(row: SeniorRow): Group?               // null for "draft"
fun panel(rows: List<SeniorRow>): List<Pair<Group, List<SeniorRow>>>   // Group order, empty groups dropped
data class Counts(val red: Int, val yellow: Int, val toResolve: Int, val drafts: Int)
fun countsOf(rows: List<SeniorRow>): Counts
enum class Action { CallAgain, Withdraw, Sign, Edit }
fun actionsFor(page: SeniorPage): List<Action>    // the medic's own patient
fun signable(page: SeniorPage): Boolean           // state in draft/submitted/accepted and signedAt == null
data class Stage(@StringRes val label: Int, val at: String?, val reached: Boolean)
fun stagesOf(page: SeniorPage): List<Stage>
```

(`Group`, `Action` are app-side enums built from strings, never decoded.)

Rules, from the design's "Monitorizare" and "The patient":
- `Urgent`: `active` with code `red` or `yellow`. Order: red before yellow, then `since` oldest first (parse with `Instant.parse`; null last).
- `ToResolve`: `wrong_number`, `unreachable`. `InProgress`: `accepted`. `Green`: `active` with any other code or none. `AtDas`: `submitted`. `Inactive`: `refused`, `withdrawn`, and any state this build doesn't know. Within non-urgent groups keep the API's order.
- `countsOf.drafts` counts `draft`.
- `actionsFor`: `wrong_number`/`unreachable` → `[CallAgain, Edit]`; `active` → `[Withdraw, Edit]`; `submitted`/`accepted` → `[Sign, Edit]` if `signable` else `[Edit]`; any other state past draft → `[Edit]`; `draft` → `[]`.
- `stagesOf`: Ciornă (`createdAt`), Trimis (`submittedAt`), Acceptat (`acceptedAt`), Activ (`consentGivenAt`); `reached` from the state (submitted ⇒ first two, accepted/wrong_number/unreachable ⇒ three, active ⇒ four, refused/withdrawn ⇒ as far as the dates go). End states append a fifth stage: `refused` → Refuzat at `consent.at`; `withdrawn` → Retras at `consent.at`; `wrong_number` → Număr greșit, `unreachable` → Nu a putut fi contactat, both `at = null`, `reached = true`.

Strings: `group_urgent` „Roșu și galben”, `group_to_resolve` „De rezolvat”, `group_in_progress` „În progres”, `group_green` „Verde”, `group_at_das` „La DAS”, `group_inactive` „Inactivi”, `stage_draft` „Ciornă”, `stage_submitted` „Trimis”, `stage_accepted` „Acceptat”, `stage_active` „Activ”, `stage_refused` „Refuzat”, `stage_withdrawn` „Retras”, `stage_wrong_number` „Număr greșit”, `stage_unreachable` „Nu a putut fi contactat”.

- [ ] **Step 1: Write the failing tests** in `PanelTest`: `a red is above a yellow is above everything` (`panel(...)` first group `Urgent` with red then yellow); `the oldest red first`; `groups come in order and empty ones go` (one row per state ⇒ `[Urgent, ToResolve, InProgress, Green, AtDas, Inactive]`, draft absent); `an unknown state is inactive`; `active without a code is green`; `counts` (`Counts(red=1, yellow=2, toResolve=2, drafts=1)` for a fixture list); `actions by state` (a parametrized table of the rule above, plus `Sign` gone once `signedAt` is set); `stages for an active senior` (four reached, dates in order); `stages for a withdrawal keep the active date` (`consentGivenAt` on Activ, Retras at `consent.at`); `stages from an older API have no dates`.
- [ ] **Step 2: Run.** `./gradlew :app:testDebugUnitTest --tests 'ro.echocare.home.PanelTest'`. Expected: FAIL to compile.
- [ ] **Step 3: Implement `Panel.kt`** and the strings.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit.** `git add -A android && git commit -m "android: the medic panel's groups, actions and enrollment stages (#54, UC-12, 03 §7)"`

---

### Task 7: The signed-in name in the top bar

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/home/Frame.kt` (`TopBar`, new `LocalSignedIn`), `android/app/src/main/java/ro/echocare/home/HomeNav.kt` (provide it), `android/app/src/main/java/ro/echocare/ui/Format.kt` (new `initials`)
- Test: `android/app/src/test/java/ro/echocare/ui/FormatTest.kt`

**Interfaces:**
- Produces: `val LocalSignedIn = staticCompositionLocalOf<String?> { null }` in `Frame.kt`. `fun initials(name: String): String` in `ui/Format.kt`: drop words ending in `.` (titles such as „Dr.”), take the first letter of the first and the last remaining word, uppercase; one word gives one letter; blank gives `""`.

- [ ] **Step 1: Write the failing tests:** `initials("Dr. Ana Ionescu") == "AI"`, `initials("Maria") == "M"`, `initials("ana maria pop") == "AP"`, `initials("  ") == ""`.
- [ ] **Step 2: Run** `./gradlew :app:testDebugUnitTest --tests 'ro.echocare.ui.FormatTest'`. Expected: FAIL.
- [ ] **Step 3: Implement.** `HomeNav` wraps its `NavHost` in `CompositionLocalProvider(LocalSignedIn provides home.displayName)` (`Screen.Home` already carries `displayName`). `TopBar` shows, before `menu()`, a 28dp square with the initials (`Palette.Card` fill, 1dp `Palette.LineStrong` border) and, when the bar is at least 600.dp wide (`BoxWithConstraints`), the name in `bodyMedium`. Not clickable.
- [ ] **Step 4: Run** `./gradlew :app:testDebugUnitTest`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -am "android: the signed-in person's name in the top bar, every role (#54)"`

---

### Task 8: The medic's home and Înregistrare

**Files:**
- Create: `android/app/src/main/java/ro/echocare/home/MedicHome.kt` (screen + `MedicViewModel`), `android/app/src/main/java/ro/echocare/home/Register.kt` (screen)
- Modify: `home/Routes.kt` (routes, `homeFor`), `home/HomeNav.kt` (destinations; the form's `onDone` goes to `MedicHomeRoute` with the sent banner), `home/SeniorsScreen.kt` (drop `onNew` and `sent`: caregiver only now)
- Test: `android/app/src/test/java/ro/echocare/home/RoutesTest.kt`

**Interfaces:**
- Consumes: `countsOf` (Task 6), `api.seniors("medic")`.
- Produces: `@Serializable data object MedicHomeRoute`, `@Serializable data object MonitorRoute`, `@Serializable data object RegisterRoute`. `homeFor("medic") == MedicHomeRoute`; caregiver stays `SeniorsRoute("caregiver")`. `@HiltViewModel class MedicViewModel(api)`: `var seniors: Load<List<SeniorRow>>`, `fun reread()`; used by the home, Înregistrare and Monitorizare (Task 9) via `hiltViewModel()`.

Screen content:
- Home: `NotificationsPrompt()`, the sent banner („Trimis la DAS.”, existing string `sent`) for 5 s as `SeniorsScreen` does today, then two large tiles side by side when width ≥ 600.dp, stacked otherwise. Monitorizare tile: title „Monitorizare”, `Chip`s „{n} roșu” (`Tone.Rosu`), „{n} galben” (`Tone.Galben`), „{n} de rezolvat” (`Tone.Link`), shown only when > 0. Înregistrare tile: title „Înregistrare”, „{n} ciorne nefinalizate” when > 0, else „Pacient nou”. Tiles: `Palette.Card`, 2dp `Palette.Line` border, label flush left, whole tile clickable.
- Înregistrare: `SnButton` „Pacient nou” → `EnrollRoute()`; under a section label „Ciorne”, the `draft` rows newest `createdAt` first, each opening `EnrollRoute(id)`; none → no section.

Strings: `monitor` „Monitorizare”, `register` „Înregistrare”, `count_red` „%d roșu”, `count_yellow` „%d galben”, `count_to_resolve` „%d de rezolvat”, `drafts_left` „%d ciorne nefinalizate”, `drafts` „Ciorne”. Title of the home: existing `medic_home` „Pacienții mei”.

- [ ] **Step 1: Write the failing tests** in `RoutesTest`: `the medic lands on the medic home` (`homeFor("medic") == MedicHomeRoute`), `the caregiver still lands on their seniors`.
- [ ] **Step 2: Run** `./gradlew :app:testDebugUnitTest --tests 'ro.echocare.home.RoutesTest'`. Expected: FAIL.
- [ ] **Step 3: Implement** the routes, `MedicViewModel`, the two screens, and `HomeNav` destinations (`MonitorRoute` can point at a placeholder `Text` until Task 9).
- [ ] **Step 4: Run** `./gradlew :app:testDebugUnitTest :app:lint`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -am "android: the medic's home, Monitorizare and Înregistrare (#54, UC-01, UC-12)"`

---

### Task 9: Monitorizare, list and detail

**Files:**
- Create: `android/app/src/main/java/ro/echocare/home/Monitor.kt` (screen, `PatientCard`, `PlaceholderCards`)
- Modify: `home/HomeNav.kt` (`MonitorRoute` destination), `home/SeniorScreen.kt` (extract `PatientPane(id: String, onEdit: (String) -> Unit)`: the page's body without its scaffold, used by both the page and the right pane)

**Interfaces:**
- Consumes: `MedicViewModel` (Task 8), `panel`, `groupOf` (Task 6), `SeniorViewModel` (exists, keyed: `hiltViewModel(key = id)`).
- Produces: `const val TWO_PANE_MIN = 840` (dp) in `Monitor.kt`. `MedicViewModel.selected: String?` stored in `SavedStateHandle` under `"selected"`, `fun select(id: String?)`.

Behaviour:
- Width ≥ `TWO_PANE_MIN`: `Row` with the list at 40% and `PatientPane(selected)` at 60%, separated by a 2dp `Palette.Line` rule; nothing selected → `Message("Alegeți un pacient.")`. Tapping a card selects it (outline 2dp `Palette.Link`). Narrower: tapping navigates to `SeniorRoute(id)`.
- The list: for each `(group, rows)` from `panel`, a section label (`group.title`) and the cards. `Inactive` starts collapsed, with „Arată (n)” / „Ascunde” as a `Kind.Link` button.
- `PatientCard`: 4dp left bar and tint: `Urgent` red → `Palette.Rosu` bar, `Tone.Rosu.fill` background; yellow → `Galben`; `ToResolve` → `Palette.Link` bar; `Inactive` → content at 60% alpha; others `Palette.Line` bar on `Palette.Card`. Content: code chip (`CodeLabel`) or state chip (`StateLabel`), form of address (`titleMedium`), full name, the reason or the state sentence („Număr greșit”, „Nu a putut fi contactat”, „Apel de bun venit în curs” for `accepted`), the time where the design gives one (`since` for a code, `submittedAt` for La DAS, relative as `das/Incidents.kt` formats it), and a watch chip when `watchState` is `not_worn`/`offline` (reuse `watchChip` from `SeniorScreen.kt`).
- Loading: `PlaceholderCards(6)`, grey `Palette.Card` boxes, no spinner. Empty (no row outside draft): `Message("Încă nu aveți pacienți.")` with `SnButton("Înregistrare")` → `RegisterRoute`.
- Rereads like every list (`RereadWhileShown(vm::reread)`).

Strings: `pick_patient` „Alegeți un pacient.”, `no_patients_yet` „Încă nu aveți pacienți.”, `show_n` „Arată (%d)”, `hide` „Ascunde”, `says_wrong_number` „Număr greșit”, `says_unreachable` „Nu a putut fi contactat”, `says_welcome_pending` „Apel de bun venit în curs”.

- [ ] **Step 1: Implement** the screen and the `PatientPane` extraction (behaviour of `SeniorScreen` unchanged for caregivers and the senior; the extraction is checked by the existing tests and lint).
- [ ] **Step 2: Run** `./gradlew :app:testDebugUnitTest :app:lint :app:assembleDebug`. Expected: PASS.
- [ ] **Step 3: Look at it.** Install on a tablet emulator in landscape against the local stack with `uv run python scripts/seed.py`, open Monitorizare, screenshot; then a phone emulator. Fix what one look shows before looking again.
- [ ] **Step 4: Commit.** `git commit -am "android: Monitorizare, by need, list and detail on a tablet (#54, UC-12)"`

---

### Task 10: The patient: stages, consent, transcripts, actions

**Files:**
- Modify: `home/SeniorScreen.kt` (`PatientPane` content), `home/SeniorViewModel.kt` (commands, transcripts), `das/IncidentScreen.kt` (make `Transcript(call: IncidentCall)` `internal` so the medic's page reuses it)
- Create: `home/Commands.kt` (pure: `commandOutcome`)
- Test: `android/app/src/test/java/ro/echocare/home/CommandsTest.kt`

**Interfaces:**
- Consumes: `actionsFor`, `stagesOf` (Task 6); `api.callAgain`, `api.withdraw`, `api.transcript` (Task 5); `refusalOf` (enroll/Refusal.kt).
- Produces: `sealed interface Outcome { data object Done; data class Refused(val reason: String?); data object Offline }` and `fun commandOutcome(status: Int?, body: String?): Outcome` in `Commands.kt` (2xx → `Done`; 409/403/404 → `Refused(reason from refusalOf)`; no status → `Offline`). On `SeniorViewModel`: `var busy: Boolean`, `var notice: Outcome?`, `fun callAgain(id: String)`, `fun withdraw(id: String)`, `var numberChanged: Boolean` (set by the screen when it returns from an edit that changed `phone` on a `wrong_number`/`unreachable` senior), `val transcripts: Map<String, Load<IncidentCall>>`, `fun openTranscript(callId: String)`.

Behaviour (the design's "The patient"):
- Stages row under the name: one cell per `Stage`, 3dp top rule `Palette.Verde` when reached, `Palette.Line` and `FgSubtle` text when not, label over date (`d MMM`).
- Consent line: `consent` as „{decision} · {method} · {date}” with Romanian labels (`given` „Dat”, `refused` „Refuzat”, `withdrawn` „Retras”; `call` „la apel”, `app` „în aplicație”, `medic` „de medic”, `das` „de DAS”; unknown shown raw), and „Semnat pe tabletă · {date}” when `signedAt` is set.
- Actions from `actionsFor`, as `SnButton`s in a `FlowRow`: `CallAgain` „Sună din nou” (`Kind.Success`, disabled while `busy`, no confirmation); `Withdraw` „Retragere consimțământ” (`Kind.Danger`); `Sign` „Semnătură” (opens the consent section of Task 11 inline); `Edit` „Editează datele” → `EnrollRoute(id)`.
- Withdrawal dialog: title „Retrageți consimțământul pentru {formOfAddress}?”, text „Nu va mai primi apeluri. Nu se poate anula.”, buttons „Retrage” and „Renunță”.
- After any command: `Done` → reread (the patient moves group); `Refused` → `Banner` with the refusal's text (`wrong_state` „Starea pacientului s-a schimbat între timp.”) and reread; `Offline` → `Banner` „Fără conexiune. Încercați din nou.”
- `numberChanged` → `Banner` „Numărul a fost schimbat. Apăsați «Sună din nou» ca să-l sunăm.”, `Tone.Link`.
- Calls: the whole list (not `recentCalls`' short one) when the viewer is the medic; each row has „Transcriere”, which loads `api.transcript(id)` once and shows `Transcript(call)` under the row; „Ascunde” folds it.

Strings: as quoted above, keys `call_again`, `withdraw`, `withdraw_title`, `withdraw_text`, `withdraw_confirm`, `cancel`, `sign`, `edit_data`, `changed_state`, `offline_retry`, `number_changed`, `transcript`, `signed_on_tablet`, `consent_*`.

- [ ] **Step 1: Write the failing tests** in `CommandsTest`: `200 is done`, `409 wrong_state is refused with its reason` (body `{"detail":{"reason":"wrong_state"}}`), `no answer is offline`.
- [ ] **Step 2: Run** `./gradlew :app:testDebugUnitTest --tests 'ro.echocare.home.CommandsTest'`. Expected: FAIL.
- [ ] **Step 3: Implement** `Commands.kt`, the view-model functions (each wraps the call so an `HttpException` gives its status and error body to `commandOutcome`, as `enroll/EnrollViewModel.command` does), and the pane.
- [ ] **Step 4: Run** `./gradlew :app:testDebugUnitTest :app:lint`. Expected: PASS.
- [ ] **Step 5: Look at it** on the tablet emulator: a red patient's transcript, „Sună din nou” on a seeded `unreachable` senior (moves to „În progres”), a withdrawal with its dialog.
- [ ] **Step 6: Commit.** `git commit -am "android: the patient: stages, consent, transcripts, Sună din nou, withdrawal (#54, UC-04, UC-12)"`

---

### Task 11: The signature

**Files:**
- Create: `android/app/src/main/java/ro/echocare/enroll/Signature.kt` (pure: points, normalise, thin, form), `android/app/src/main/java/ro/echocare/enroll/SignaturePad.kt` (`ConsentSection` composable)
- Modify: `enroll/EnrollScreen.kt` (`ReviewStep`), `enroll/EnrollViewModel.kt` (`sign`), `home/SeniorScreen.kt` and `home/SeniorViewModel.kt` (`Sign` action opens `ConsentSection`; `sign`), `res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/enroll/SignatureTest.kt`

**Interfaces:**
- Produces:

```kotlin
const val SIGNATURE_VERSION = "v1-semnatura"
const val MAX_POINTS = 5000
data class Point(val x: Float, val y: Float)
fun normalised(strokes: List<List<Point>>, width: Float, height: Float): List<List<Point>>  // each coordinate / size, clamped to 0..1
fun thinned(strokes: List<List<Point>>, max: Int = MAX_POINTS): List<List<Point>>           // ≤ max points; every stroke keeps its first and last
fun signatureForm(strokes: List<List<Point>>, width: Float, height: Float): SignatureForm    // normalised, thinned, empty strokes dropped, SIGNATURE_VERSION
@Composable fun ConsentSection(signedAt: String?, busy: Boolean, onSave: (List<List<Point>>, Float, Float) -> Unit)
```

`EnrollViewModel.sign(strokes, width, height)` and `SeniorViewModel.sign(id, strokes, width, height)` post `api.sign(id, signatureForm(...))` and reread on success.

Behaviour:
- `ConsentSection`: label „Consimțământ (opțional, se confirmă și la apelul de bun venit) · v1-semnatura”, the text `consent_signature_text` (exact text in Global Constraints), a pad 200dp tall on `Palette.Inset` with a 2dp dashed `Palette.LineStrong` border and „Semnați aici” as a hint until drawn, „Șterge” (clears) and „Salvează semnătura” (`Kind.Success`, disabled while empty or `busy`). Strokes drawn with `pointerInput`/`detectDragGestures`; a tap is a one-point stroke. Once `signedAt` is set: „Semnat · {date}” instead of the pad.
- In `ReviewStep`, below `SeniorDetails`, when `signable(senior)`. On the patient page, under the actions, when `Sign` was pressed.
- A failed save keeps the drawing and shows a `Banner`.

- [ ] **Step 1: Write the failing tests** in `SignatureTest`: `points are shares of the pad` (`normalised(listOf(listOf(Point(50f, 25f))), 100f, 50f) == listOf(listOf(Point(0.5f, 0.5f)))`); `points outside the pad are clamped` (`Point(-3f, 70f)` on 100×50 → `Point(0f, 1f)`); `a tap is one point`; `a long signature is thinned to at most 5000 and keeps each stroke's ends` (3 strokes of 4,000 points: total ≤ 5000, each first and last kept); `a short signature is untouched`; `the form carries v1-semnatura` and drops an empty stroke.
- [ ] **Step 2: Run** `./gradlew :app:testDebugUnitTest --tests 'ro.echocare.enroll.SignatureTest'`. Expected: FAIL.
- [ ] **Step 3: Implement** `Signature.kt`, then the composable and both view-model `sign`s.
- [ ] **Step 4: Run** `./gradlew :app:testDebugUnitTest :app:lint`. Expected: PASS.
- [ ] **Step 5: Look at it:** sign on step 4 of a new draft without a caregiver (it saves), and on a `submitted` patient's page.
- [ ] **Step 6: Commit.** `git commit -am "android: the optional signature under its consent text (#54, G7, UC-01 step 5)"`

---

### Task 12: End-to-end check

- [ ] **Step 1:** From the repo root, `docker compose up --watch`, then `cd backend && uv run python scripts/seed.py --reset`. Make sure the seed has a red, a yellow, a green, an `unreachable` and a `wrong_number` senior for the seeded medic; if not, add them to `scripts/seed.py` in this task and commit that with the check.
- [ ] **Step 2:** Tablet emulator, landscape, debug APK pointed at the local stack (`android/AGENTS.md` commands). As the medic: the home shows the counts; Monitorizare shows the red patient above the green one; open the red one's transcript; press „Sună din nou” on the `unreachable` senior: it moves to „În progres”, and the senior's app shows the welcome card. Withdraw an active senior. Sign a submitted one. Rotate to portrait and back: the selection stays.
- [ ] **Step 3:** Phone emulator: home tiles stack, Monitorizare is a list that opens the patient page.
- [ ] **Step 4:** Screenshots of steps 2 and 3 for the PR. Ask the user before pushing either branch or opening PRs (backend first; Android's PR after the backend's is merged, since its CI and Railway's wait-for-CI are per commit).
