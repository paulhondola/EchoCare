# DAS role in the Android app — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder DAS home with the incident list, the incident page, and Preiau / Rezolvat, against the existing API.

**Architecture:** A new `ro.echocare.das` package. Pure logic (sorting, relative time, the senior's words, the Maps URI, which action a status allows, what a refusal says) lives in one file tested on the JVM. Three screens, each with its own Hilt ViewModel, are built from the existing `Load`/`answer`, `send`/`refusalOf`, `HomeScaffold`, `LoadBody`, `RereadWhileShown` and `ui/Components.kt`. Two type-safe routes are added to `HomeNav`.

**Tech Stack:** Kotlin, Jetpack Compose, Navigation Compose (type-safe routes), Hilt, Retrofit with kotlinx.serialization, JUnit 4.

**Spec:** [docs/superpowers/specs/2026-10-22-das-android-design.md](../specs/2026-10-22-das-android-design.md). Read it with this plan.

## Global Constraints

- Android only. Nothing under `backend/`, `dashboard/` or `docs/specs/echocare/` changes.
- New UI text is Romanian, in `app/src/main/res/values/strings.xml`. Code and comments are English and cite the spec by ID (`UC-11`, `04 §1`, `design §…` for the design doc).
- Status, outcome, trigger, event type, speaker and severity are decoded as `String`, never a Kotlin `enum` (app/AGENTS.md, ADR-001 §2.3). An unknown value shows as raw text or no label.
- Reads use `answer { … }` (home/Load.kt). Commands use `send { … }` (enroll/Refusal.kt): `failureOf` turns a 409 into `NoConnection`, `refusalOf` does not.
- Build from `Palette`, `Tone`, `Chip`, `SnButton`, `FieldRow`, `PhoneNumber`, `CallButton`, `SectionLabel`, `Rule`, `Banner`. No stock Material buttons or cards. Don't use `Palette.FgSubtle` for text a dispatcher has to read.
- Times show in the device zone (`ZoneId.systemDefault()`). The API sends UTC ISO-8601, possibly with microseconds and `+00:00`.
- `./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug` from `android/` passes after every task. The lefthook pre-commit runs `ktlintFormat`; commit with hooks on.

## Review Focus

1. **A newer server sends an unknown status, trigger, event type or speaker.** The list drops a status it doesn't know, the page shows no action button for it, and labels fall back to the raw value. Pinned in Task 1 (`unknownStatusIsLeftOut`) and Task 3 (`onlyOpenAndInProgressHaveAnAction`).
2. **An incident with no calls, no reports, or a red report without a quote.** The page shows no quote line and the "no calls" text, and doesn't crash. Pinned in Task 2 (`noRedQuoteMeansNoWords`, `timelineOfACallWithNoTurns`).
3. **Someone resolves the incident while the page is open.** The next read shows `resolved` and the bottom bar shows nothing. Pinned in Task 3 (`onlyOpenAndInProgressHaveAnAction`).
4. **FastAPI timestamps with microseconds and `+00:00`.** Relative time and sorting parse them. Pinned in Task 1 (`agoReadsFastApiTimestamps`).
5. **A senior with no street and an event with no coordinates.** "Deschide în Hărți" is hidden rather than opening an empty search. Pinned in Task 2 (`noPlaceMeansNoMapsLink`).

## Deviation from the design, decided here

The design's call button says **Sună**. The app already has `CallButton` (`ACTION_DIAL`, no permission, label "Apelează", the same word the dashboard uses), so the incident page reuses it unchanged.

---

### Task 1: API, incident list, DAS home

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/Api.kt`: incident data classes and four endpoints
- Create: `android/app/src/main/java/ro/echocare/das/Incidents.kt`: pure logic, grown by Tasks 2–3
- Create: `android/app/src/main/java/ro/echocare/das/IncidentsViewModel.kt`
- Create: `android/app/src/main/java/ro/echocare/das/IncidentsScreen.kt`
- Modify: `android/app/src/main/java/ro/echocare/home/Routes.kt`: add `IncidentRoute`, update the `IncidentsRoute` doc comment
- Modify: `android/app/src/main/java/ro/echocare/home/HomeNav.kt:85-89`: `IncidentsRoute` shows `IncidentsScreen`
- Modify: `android/app/src/main/res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/ApiTest.kt`, `android/app/src/test/java/ro/echocare/das/IncidentsTest.kt`
- Also commit: `docs/superpowers/specs/2026-10-22-das-android-design.md`, this plan

**Interfaces:**
- Produces (Api.kt, all `@Serializable`, snake_case via `@SerialName`, nullable fields default `null`, lists default `emptyList()`):
  - `IncidentRow(id: String, seniorName: String /*senior_full_name*/, formOfAddress: String /*senior_form_of_address*/, status: String, reason: String, openedAt: String, takenByName: String?, takenAt: String?, handoverAnswered: Boolean = false)`
  - `IncidentPage(id: String, status: String, reason: String, openedAt: String, takenByName: String?, handoverAnswered: Boolean = false, senior: IncidentSenior, caregivers: List<IncidentCaregiver>, event: TriggerEvent?, calls: List<IncidentCall>)`
  - `IncidentSenior(id, fullName, formOfAddress, phone /*phone_e164*/, landline: Boolean /*phone_is_landline*/, street?, streetNumber?, block?, staircase?, floor?, apartment?, intercomCode?, keyHolder?, landmark?)`
  - `IncidentCaregiver(displayName: String, phone: String /*phone_e164*/, relation: String?)`. The existing `Caregiver` needs `user_id`, which incidents don't send.
  - `TriggerEvent(type: String, measuredAt: String, latitude: Double?, longitude: Double?, accuracy: Double? /*location_accuracy_m*/)`
  - `IncidentCall(id: String, trigger: String, attempt: Int, state: String, startedAt: String?, finalSeverity: String?, handoverAnswered: Boolean?, reports: List<CallReport>, turns: List<CallTurn>)`
  - `CallReport(severity: String, reason: String, quote: String?, at: String)`, `CallTurn(speaker: String, content: String, at: String)`
  - `Resolution(outcome: String, note: String)`
  - `EchoCareApi`: `@GET("incidents") suspend fun incidents(@Query("status") status: String): List<IncidentRow>`, `@GET("incidents/{id}") suspend fun incident(@Path("id") id: String): IncidentPage`, `@POST("incidents/{id}/take") suspend fun take(@Path("id") id: String): IncidentRow`, `@POST("incidents/{id}/resolve") suspend fun resolve(@Path("id") id: String, @Body body: Resolution): IncidentRow`
  - Incidents.kt: `const val ACTIVE = "open,in_progress"`; `data class Sections(val open: List<IncidentRow>, val inProgress: List<IncidentRow>)`; `fun sections(rows: List<IncidentRow>): Sections`; `sealed interface Ago { data object Moments; data class Minutes(val m: Long); data class Hours(val h: Long, val m: Long); data class On(val at: Instant) }`; `fun ago(iso: String, now: Instant): Ago`
  - Routes.kt: `@Serializable data class IncidentRoute(val id: String)`
  - `IncidentsScreen(menu: @Composable () -> Unit, onOpen: (String) -> Unit, onSessionEnd: (Failure) -> Unit, vm: IncidentsViewModel = hiltViewModel())`

- [ ] **Step 1: Branch and commit the design**

```bash
git switch -c das-android
git add docs/superpowers/specs/2026-10-22-das-android-design.md docs/superpowers/plans/2026-10-22-das-android.md
git commit -m "docs: design and plan for the DAS role in the Android app"
```

- [ ] **Step 2: Write the failing tests**

`ApiTest.anIncidentPageIsDecoded`: decode this body (the shape the local API serves, with an extra unknown key) into `IncidentPage` and assert `senior.street == "Strada Bucovinei"`, `event?.accuracy == 14.0`, `calls.single().handoverAnswered == null`, `calls.single().reports.single().quote == "Mă strânge în piept și nu pot respira bine."`, and `caregivers.single().relation == "fiică"`.

```json
{"id":"92a0","status":"open","reason":"Durere în piept, greutate la respirație",
 "opened_at":"2026-10-22T19:06:55.123456+00:00","taken_by_name":null,"taken_at":null,
 "resolved_by_name":null,"resolved_at":null,"outcome":null,"note":null,"handover_answered":false,
 "future_field":1,
 "senior":{"id":"s1","full_name":"Dumitru Pop","form_of_address":"domnul Dumitru",
   "phone_e164":"+40700000113","phone_is_landline":false,"street":"Strada Bucovinei",
   "street_number":"27","block":"H4","staircase":"A","floor":"5","apartment":"31",
   "intercom_code":"31","key_holder":"Fiica, Simona, are cheie de rezervă",
   "landmark":"Lângă parcul din cartier"},
 "caregivers":[{"display_name":"Simona Pop","phone_e164":"+40700000211","relation":"fiică"}],
 "event":{"type":"sos_button","measured_at":"2026-10-22T19:05:00+00:00","latitude":45.7489,
   "longitude":21.2087,"location_accuracy_m":14,"located_at":null},
 "calls":[{"id":"c1","trigger":"watch","attempt":1,"state":"handed_over",
   "started_at":"2026-10-22T19:06:30+00:00","ended_at":null,"final_severity":"red",
   "final_certainty":null,"reason":null,"summary":null,"handover_answered":null,
   "reports":[{"source":"agent","severity":"red","certainty":null,
     "reason":"Durere în piept, greutate la respirație",
     "quote":"Mă strânge în piept și nu pot respira bine.","at":"2026-10-22T19:06:42+00:00"}],
   "turns":[{"speaker":"senior","kind":"speech",
     "content":"Mă strânge în piept și nu pot respira bine.","at":"2026-10-22T19:06:41+00:00"}]}]}
```

`IncidentsTest` (new, package `ro.echocare.das`), with a `row(id, status, openedAt, takenAt = null)` helper:
- `openComeFirstOldestFirst`: rows opened 19:15, 19:06, 18:29 (all `open`) → `sections(rows).open.map { it.id } == listOf("18:29", "19:06", "19:15")`, using the open time as the id.
- `inProgressSortsByTakeTimeThenOpenTime`: A opened 18:00 taken 19:00; B opened 18:30, `takenAt` null → `inProgress` ids `["B", "A"]`. B's fallback 18:30 is before A's 19:00.
- `unknownStatusIsLeftOut`: statuses `resolved` and `archived` appear in neither section.
- `agoBoundaries` with `now = Instant.parse("2026-10-22T20:00:00Z")`: 30 s ago → `Ago.Moments`; 59 min → `Ago.Minutes(59)`; 60 min → `Ago.Hours(1, 0)`; 23 h 59 min → `Ago.Hours(23, 59)`; 24 h → `Ago.On(that instant)`; an instant after `now` (clock skew) → `Ago.Moments`.
- `agoReadsFastApiTimestamps`: `ago("2026-10-22T19:06:55.123456+00:00", now) == Ago.Minutes(53)`.

- [ ] **Step 3: Run the tests to see them fail**

Run: `./gradlew :app:testDebugUnitTest --tests 'ro.echocare.das.*' --tests 'ro.echocare.ApiTest'`
Expected: compilation fails, because `IncidentPage`, `sections` and `ago` don't exist.

- [ ] **Step 4: Implement the data classes, endpoints, `sections` and `ago`**

`sections`: keep `open` sorted by `Instant.parse(openedAt)` and `in_progress` by `Instant.parse(takenAt ?: openedAt)`, both ascending; drop every other status. `ago`: from `Duration.between(at, now)`; under 1 min (or negative) `Moments`, under 60 min `Minutes`, under 24 h `Hours(h, m)`, otherwise `On(at)`.

- [ ] **Step 5: Run the tests to see them pass**

Run: the Step 3 command. Expected: PASS.

- [ ] **Step 6: Build the list**

- `IncidentsViewModel @Inject constructor(api: EchoCareApi)`: `var incidents by mutableStateOf<Load<List<IncidentRow>>>(Load.Loading)`, and `fun reread()` doing `incidents = incidents.after(answer { api.incidents(ACTIVE) })`, as `SeniorsViewModel` does.
- `IncidentsScreen`: `RereadWhileShown(vm::reread)`. `HomeScaffold(stringResource(R.string.role_das), onBack = null, menu)` around `LoadBody`. Empty → `Message(stringResource(R.string.no_incidents))`. Otherwise a `LazyColumn` with `SectionLabel("Deschise · n")`, then cards, then `SectionLabel("În lucru · n")`, then cards, leaving out a section that's empty. A card looks like `SeniorCard` (3 dp `Tone.Rosu` bar, `Palette.Card`, clickable) and shows: `seniorName` (titleMedium), `reason`, then a row with the `Ago` text, the status chip (open: `Chip("Deschis", Tone.Rosu)`; in progress: `Chip("Preluat de {takenByName}", Tone.Link)`), and the hand-over chip (`Chip("Transferat la DAS", Tone.Verde)` when true, `Chip("Nepreluat", Tone.Galben)` when false). `Ago.On` is formatted `dd.MM.yyyy HH:mm` in the device zone. `now` is `Instant.now()` read at composition; the timed re-read recomposes it.
- `HomeNav`: `composable<IncidentsRoute> { IncidentsScreen(menu, onOpen = { nav.navigate(IncidentRoute(it)) }, onSessionEnd) }`. Register `composable<IncidentRoute> { }` with an empty body for now; Task 2 fills it.

New strings:

```xml
<string name="incidents_open">Deschise · %1$d</string>
<string name="incidents_in_progress">În lucru · %1$d</string>
<string name="status_open">Deschis</string>
<string name="status_taken_by">Preluat de %1$s</string>
<string name="status_resolved">Rezolvat</string>
<string name="ago_moments">acum câteva secunde</string>
<string name="ago_minutes">acum %1$d min</string>
<string name="ago_hours">acum %1$d h %2$d min</string>
<string name="handover_yes">Transferat la DAS</string>
<string name="handover_no">Nepreluat</string>
```

- [ ] **Step 7: Check the whole build and look at it on the emulator**

Run: `./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug` → BUILD SUCCESSFUL. Then `android run --device=emulator-5554 --apks=app/build/outputs/apk/debug/app-debug.apk --install-options=-g` with the seeded stack up, signed in as DAS Test. Expected: 4 cards under "Deschise · 4" in the order Aurelia Marinescu, Dumitru Pop, Ion Dumitrescu, Teodor Crișan, and 4 under "În lucru · 4". Capture a screenshot with `android screen capture`.

- [ ] **Step 8: Commit**

```bash
git add android/app/src
git commit -m "android: DAS home lists open and in-progress incidents (UC-12)"
```

---

### Task 2: The incident page

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/das/Incidents.kt`
- Create: `android/app/src/main/java/ro/echocare/das/IncidentViewModel.kt`
- Create: `android/app/src/main/java/ro/echocare/das/IncidentScreen.kt`
- Modify: `android/app/src/main/java/ro/echocare/home/SeniorScreen.kt`: `place(senior: SeniorPage)` becomes an internal `place(street, streetNumber, block, staircase, floor, apartment)` that both pages call
- Modify: `android/app/src/main/java/ro/echocare/home/HomeNav.kt`: fill `composable<IncidentRoute>`
- Modify: `android/app/src/main/res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/das/IncidentsTest.kt`

**Interfaces:**
- Consumes: the Task 1 data classes and `IncidentRoute(id)`.
- Produces (Incidents.kt):
  - `fun seniorsWords(calls: List<IncidentCall>): String?`: the `quote` of the latest red report (by `at`) that has a non-blank quote, across all calls.
  - `fun newestFirst(calls: List<IncidentCall>): List<IncidentCall>`: calls with no `startedAt` first, then by `startedAt` descending.
  - `fun callLive(calls: List<IncidentCall>): Boolean`: any `state` is `ringing` or `in_progress`.
  - `sealed interface Line { val at: String; data class Said(val turn: CallTurn); data class Flagged(val report: CallReport) }` and `fun timeline(call: IncidentCall): List<Line>`: turns and reports merged by `Instant.parse(at)`; at equal times the turn comes first.
  - `const val CITY = "Timișoara"` and `fun mapsUri(senior: IncidentSenior, event: TriggerEvent?): String?`
- `IncidentViewModel @Inject constructor(api, saved: SavedStateHandle)`: `val id = saved.toRoute<IncidentRoute>().id`, `var page: Load<IncidentPage>`, `fun reread()`. Task 3 adds `take()`.
- `IncidentScreen(onBack: () -> Unit, onResolve: (String) -> Unit, onSessionEnd: (Failure) -> Unit, vm: IncidentViewModel = hiltViewModel())`

- [ ] **Step 1: Write the failing tests** (in `IncidentsTest`)

- `seniorsWordsIsTheLatestRedQuote`: two calls, reports yellow "A" (quote "q1"), red at 19:06 (quote "q2"), red at 19:20 (quote "q3") → `"q3"`.
- `noRedQuoteMeansNoWords`: red reports with `quote = null` and `"  "`, plus a yellow with a quote → `null`. `seniorsWords(emptyList()) == null`.
- `newestCallFirst`: startedAt 18:00, 19:00, null → order `[null, 19:00, 18:00]`.
- `liveWhenRingingOrInProgress`: states `["completed", "ringing"]` → true; `["handed_over", "unanswered"]` → false.
- `timelinePutsReportsWhereTheyHappened`: turns at :34, :41, :48, report at :41 → `Said(:34), Said(:41), Flagged(:41), Said(:48)`.
- `timelineOfACallWithNoTurns`: no turns, no reports → empty list.
- `mapsUsesCoordinatesWhenThereAreAny`: event lat 45.7489, lng 21.2087 → `"geo:45.7489,21.2087?q=45.7489,21.2087"`.
- `mapsFallsBackToTheAddress`: event null, street "Strada Bucovinei", number "27" → `"geo:0,0?q=Strada%20Bucovinei%2027%2C%20Timi%C8%99oara"`.
- `noPlaceMeansNoMapsLink`: street null and event without coordinates → `null`.

- [ ] **Step 2: Run the tests to see them fail**

Run: `./gradlew :app:testDebugUnitTest --tests 'ro.echocare.das.*'`. Expected: compilation fails.

- [ ] **Step 3: Implement the five functions**

`mapsUri`: coordinates win. Otherwise the query is `"{street} {number}, $CITY"` (number left out when null), encoded with `URLEncoder.encode(q, UTF_8).replace("+", "%20")`. With no street and no coordinates, return `null`.

- [ ] **Step 4: Run the tests to see them pass**

Run: the Step 2 command. Expected: PASS.

- [ ] **Step 5: Build the page**

`IncidentScreen`: `RereadWhileShown(vm::reread)`. `HomeScaffold(senior.fullName or "", onBack, menu = {})` around `LoadBody`. A `Column` fills the space, with a `verticalScroll` content area taking `Modifier.weight(1f)` and the pinned bar below it (empty in this task). Sections in the design's order (design §"The incident page"):
1. A status chip as on the list (`Rezolvat` with `Tone.Verde` for resolved; a status it doesn't know shows the raw value with `Tone.Muted`); `Chip("Apel în curs", Tone.Galben)` when `callLive`; `reason` as titleLarge; `seniorsWords` in „…” on a `Palette.Card` block with a 3 dp `Tone.Rosu` bar.
2. `SectionLabel("Adresă și acces")`: `FieldRow(label_address)` with `place(…)`, then `label_intercom`, `label_key_holder` and `label_landmark` rows when present (as `SeniorDetails` does), then `SnButton("Deschide în Hărți", kind = Kind.Link)` when `mapsUri` isn't null. It starts `Intent(ACTION_VIEW, uri.toUri())` and catches `ActivityNotFoundException`.
3. `SectionLabel("Telefon")`: the senior row (`PhoneNumber(phone, landline)` + `CallButton`), then each caregiver as `"{name} · {relation}"` + `formatPhone` + `CallButton`, with the same layout as the caregivers in `SeniorDetails`.
4. When `event` is present, `SectionLabel("Eveniment")`: `Tip` (the event-type label, or the raw type), `Măsurat la` (`HH:mm`), and `Locație` (`"{lat}, {lng} · ±{accuracy} m"`, the accuracy rounded to an `Int` for `%3$d`) when there are coordinates.
5. `SectionLabel("Apeluri")`. With no calls, the `no_calls` text. Otherwise `newestFirst`: the first expanded, the rest collapsed to one clickable line `"{trigger label} · încercarea {attempt} · {severity label}"` that toggles open (`remember { mutableStateMapOf<String, Boolean>() }`). An expanded call lists `timeline(call)`: `Said` as the speaker label (`senior` → Senior, `agent` → Sistem AI, else Sistem), a mono `HH:mm:ss` time and the content; `Flagged` as a `Tone.Rosu`/`Tone.Galben`/`Tone.Verde` tinted line `"{Cod …} · semnalat — {reason}"`. Under the timeline, when `handoverAnswered != null`: `handover_call_yes` / `handover_call_no`.

`HomeNav`: `composable<IncidentRoute> { IncidentScreen(onBack = { nav.popBackStack() }, onResolve = { }, onSessionEnd) }`. Task 3 wires `onResolve`.

New strings:

```xml
<string name="call_live">Apel în curs</string>
<string name="section_access">Adresă și acces</string>
<string name="open_in_maps">Deschide în Hărți</string>
<string name="section_event">Eveniment</string>
<string name="event_type">Tip</string>
<string name="event_measured_at">Măsurat la</string>
<string name="event_location">Locație</string>
<string name="event_location_value">%1$s, %2$s · ±%3$d m</string>
<string name="section_calls">Apeluri</string>
<string name="no_calls">Niciun apel înregistrat pentru acest incident.</string>
<string name="call_line">%1$s · încercarea %2$d · %3$s</string>
<string name="speaker_senior">Senior</string>
<string name="speaker_agent">Sistem AI</string>
<string name="speaker_system">Sistem</string>
<string name="flagged">%1$s · semnalat — %2$s</string>
<string name="handover_call_yes">Transferat la telefonul de serviciu DAS</string>
<string name="handover_call_no">Transferul nu a fost preluat</string>
<string name="trigger_campaign">Campanie</string>
<string name="trigger_watch">Ceas</string>
<string name="trigger_manual">Cerere „Sunați-mă”</string>
<string name="trigger_welcome">Apel de bun venit</string>
<string name="event_sos_button">Buton SOS</string>
<string name="event_fall">Cădere detectată</string>
<string name="event_high_pulse_at_rest">Puls ridicat în repaus</string>
<string name="event_inactivity">Inactivitate</string>
```

The severity labels reuse `CODE_LABELS` from Routes.kt (`Cod verde` / `Cod galben` / `Cod roșu`). Put the trigger and event-type maps in Routes.kt next to `CODE_LABELS`, in the same style.

- [ ] **Step 6: Check the build and look at it on the emulator**

Run: the full check from Task 1 Step 7, then install. Open Dumitru Pop. Expected: the quote, "Strada Bucovinei 27, bl. H4, sc. A, et. 5, ap. 31", interfon 31, Simona Pop · fiică, Buton SOS ±14 m, the watch call with Cod galben then Cod roșu inline. "Deschide în Hărți" opens Maps at 45.7489, 21.2087, and Apelează opens the dialer with 0700 000 113. Take a screenshot.

- [ ] **Step 7: Commit**

```bash
git add android/app/src
git commit -m "android: DAS incident page with access, calls and transcripts (UC-11, UC-12)"
```

---

### Task 3: Preiau and Rezolvare caz

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/enroll/Refusal.kt`: `AlreadyDone` carries `taken_by_name`
- Modify: `android/app/src/main/java/ro/echocare/das/Incidents.kt`
- Modify: `android/app/src/main/java/ro/echocare/das/IncidentViewModel.kt`, `IncidentScreen.kt`
- Create: `android/app/src/main/java/ro/echocare/das/ResolveViewModel.kt`, `ResolveScreen.kt`
- Modify: `android/app/src/main/java/ro/echocare/home/Routes.kt`: add `ResolveRoute`
- Modify: `android/app/src/main/java/ro/echocare/home/HomeNav.kt`
- Modify: `android/app/src/main/res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/enroll/RefusalTest.kt`, `android/app/src/test/java/ro/echocare/das/IncidentsTest.kt`

**Interfaces:**
- Consumes: `send`, `Sent`, `Refusal`, `refusalOf` (enroll/Refusal.kt); `IncidentRow`, `Resolution`, `EchoCareApi.take`/`resolve` (Task 1).
- Produces:
  - Refusal.kt: `data class AlreadyDone(val takenByName: String? = null) : Refusal`, replacing `data object AlreadyDone`. `thenAfter` matches `is Refusal.AlreadyDone`, and its behaviour is unchanged.
  - Incidents.kt: `enum class Act { Take, Resolve }` (the app's own choice, not decoded); `fun actFor(status: String): Act?`; `sealed interface Notice { data class TakenBy(val name: String); data class Says(@StringRes val text: Int); data class Ends(val failure: Failure) }` (`ro.echocare.das.Notice`, distinct from `enroll.Notice`); `fun noticeAfter(refusal: Refusal, act: Act): Notice`; `const val NOTE_MAX = 1000`; `fun canSend(outcome: String?, note: String): Boolean`; `val OUTCOMES: List<Pair<String, Int>>`
  - Routes.kt: `@Serializable data class ResolveRoute(val id: String)`
  - `IncidentViewModel.take()` and `var notice: Notice?`
  - `ResolveViewModel`: `var outcome: String?`, `var note: String`, `var sending: Boolean`, `var notice: Notice?`, `fun submit(onDone: () -> Unit)`. Not `send`: a member `send(() -> Unit)` would capture the call to the top-level `send { … }` and recurse.
  - `ResolveScreen(onBack: () -> Unit, onDone: () -> Unit, onSessionEnd: (Failure) -> Unit, vm: ResolveViewModel = hiltViewModel())`

- [ ] **Step 1: Write the failing tests**

`RefusalTest`: replace the three `Refusal.AlreadyDone` uses with `Refusal.AlreadyDone()`, and add `alreadyDoneCarriesWhoTookIt`:
- `refusalOf(409, """{"detail":{"reason":"already_done","taken_by_name":"Cristian Pavel"}}""") == Refusal.AlreadyDone("Cristian Pavel")`
- `refusalOf(409, """{"detail":{"reason":"already_done"}}""") == Refusal.AlreadyDone(null)`

`IncidentsTest`:
- `onlyOpenAndInProgressHaveAnAction`: `actFor("open") == Act.Take`, `actFor("in_progress") == Act.Resolve`, `actFor("resolved") == null`, `actFor("archived") == null`.
- `takeRefusals`:
  - `noticeAfter(AlreadyDone("Cristian Pavel"), Act.Take) == Notice.TakenBy("Cristian Pavel")`
  - `noticeAfter(AlreadyDone(null), Act.Take) == Notice.Says(R.string.incident_changed)`
  - `noticeAfter(WrongState, Act.Take) == Notice.Says(R.string.incident_changed)`
  - `noticeAfter(Failed(NoConnection), Act.Take) == Notice.Says(R.string.send_failed)`
  - `noticeAfter(Failed(NotAllowed), Act.Take) == Notice.Says(R.string.not_allowed_action)`
  - `noticeAfter(Failed(NotFound), Act.Take) == Notice.Says(R.string.incident_gone)`
  - `noticeAfter(Failed(SignedOut), Act.Take) == Notice.Ends(Failure.SignedOut)`
  - `noticeAfter(Invalid(emptyList()), Act.Resolve) == Notice.Says(R.string.send_failed)`
- `resolveRefusals`: `noticeAfter(AlreadyDone("X"), Act.Resolve) == Notice.Says(R.string.already_resolved)`; `noticeAfter(WrongState, Act.Resolve) == Notice.Says(R.string.incident_changed)`.
- `sendNeedsAnOutcomeAndANote`: `canSend(null, "x")` false; `canSend("team_sent", "   ")` false; `canSend("team_sent", "a".repeat(1001))` false; `canSend("team_sent", "a".repeat(1000))` true.
- `outcomesInTheDashboardsOrder`: `OUTCOMES.map { it.first } == listOf("senior_ok", "team_sent", "called_112", "not_reached", "false_alarm")`.

- [ ] **Step 2: Run the tests to see them fail**

Run: `./gradlew :app:testDebugUnitTest --tests 'ro.echocare.das.*' --tests 'ro.echocare.enroll.RefusalTest'`. Expected: compilation fails.

- [ ] **Step 3: Implement**

`refusalOf` reads `ours?.get("taken_by_name").text()` into `AlreadyDone`. `noticeAfter` maps exactly as the tests list; `Incomplete` and `PhoneTaken` also give `send_failed`. `canSend` checks the trimmed note isn't empty and its length is at most `NOTE_MAX`.

- [ ] **Step 4: Run all unit tests**

Run: `./gradlew :app:testDebugUnitTest`. Expected: PASS, including every existing enroll test.

- [ ] **Step 5: Wire the actions**

- `IncidentViewModel.take()`: `send { api.take(id) }`. On `Sent.Ok` → `notice = null; reread()`. On `Sent.No` → `notice = noticeAfter(refusal, Act.Take)`, then `reread()` unless it's `Notice.Ends`. `IncidentScreen` hands `Notice.Ends` to `onSessionEnd` (`LaunchedEffect`), shows `TakenBy` as `"Preluat deja de {name}."` and `Says` as its text, in a `Banner(…, Tone.Galben)` above the pinned bar. The bar, a `Palette.Subtle` row with a 2 dp top `Rule`, shows `actFor(page.status)`: `Take` → `SnButton("Preiau", vm::take, fillMaxWidth, kind = Kind.Danger)`; `Resolve` → `SnButton("Rezolvat", { onResolve(id) }, fillMaxWidth, kind = Kind.Success)`; `null` → no bar.
- `ResolveViewModel`: reads `ResolveRoute` from `SavedStateHandle`. `submit(onDone)` returns early unless `canSend`, sets `sending`, runs `send { api.resolve(id, Resolution(outcome, note.trim())) }`. `Ok` → `onDone()`; `No` → `notice = noticeAfter(refusal, Act.Resolve)`, keeping `outcome` and `note`.
- `ResolveScreen`: `HomeScaffold("Rezolvare caz", onBack, menu = {})`. `SectionLabel("Rezultat")`, then one selectable row per `OUTCOMES` entry (`Modifier.selectable(role = Role.RadioButton)`, the Material `RadioButton` tinted `Palette.Link`, the label). Then `SectionLabel("Notă")` with `SnTextField(note, { if (it.length <= NOTE_MAX) vm.note = it }, …)` (multi-line, `KeyboardType.Text`) and a mono `"{n} / 1000"` counter. Pinned `SnButton("Trimite", …, kind = Kind.Success)`, enabled when `canSend && !sending`. `Notice.Ends` → `onSessionEnd`. It reads nothing: there's no `RereadWhileShown` here.
- `HomeNav`: `IncidentScreen(onResolve = { nav.navigate(ResolveRoute(it)) })`; `composable<ResolveRoute> { ResolveScreen(onBack = { nav.popBackStack() }, onDone = { nav.popBackStack<IncidentsRoute>(inclusive = false) }, onSessionEnd) }`.

New strings:

```xml
<string name="take">Preiau</string>
<string name="resolve">Rezolvat</string>
<string name="resolve_title">Rezolvare caz</string>
<string name="resolve_outcome">Rezultat</string>
<string name="resolve_note">Notă</string>
<string name="note_count">%1$d / 1000</string>
<string name="send">Trimite</string>
<string name="outcome_senior_ok">Senior OK</string>
<string name="outcome_team_sent">Echipaj trimis</string>
<string name="outcome_called_112">Apelat 112</string>
<string name="outcome_not_reached">Nu a răspuns</string>
<string name="outcome_false_alarm">Alarmă falsă</string>
<string name="taken_by_other">Preluat deja de %1$s.</string>
<string name="incident_changed">Incidentul s-a schimbat între timp.</string>
<string name="already_resolved">Incidentul a fost deja rezolvat.</string>
<string name="send_failed">Nu am putut trimite. Încercați din nou.</string>
<string name="not_allowed_action">Nu aveți dreptul să faceți asta.</string>
<string name="incident_gone">Incidentul nu mai există.</string>
```

None of the new string names in Tasks 1–3 exist in strings.xml today (checked when this plan was written).

- [ ] **Step 6: Check the build**

Run: `./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug`. Expected: BUILD SUCCESSFUL.

- [ ] **Step 7: Commit**

```bash
git add android/app/src
git commit -m "android: DAS takes and resolves incidents from the phone (UC-11)"
```

---

### Task 4: End-to-end walkthrough and release check

No new code unless a step fails. A failure goes back to the task that owns it, and gets its own fix commit.

- [ ] **Step 1: Reset and install**

```bash
cd backend && uv run python scripts/seed.py --reset
cd ../android && ./gradlew :app:assembleDebug
android run --device=emulator-5554 --apks=app/build/outputs/apk/debug/app-debug.apk --install-options=-g
```

Sign in as DAS Test (`+40700000001`).

- [ ] **Step 2: Walk design §Testing "E2E walkthrough" steps 1–7**

Take a screenshot at each of steps 1, 2, 4, 5 and 6 with `android screen capture --device=emulator-5554 -o step-N.png` (save to the scratchpad, don't commit). Check the dashboard at http://localhost:5173 for steps 4 and 5. Expected: every step's stated result. Record any step skipped and why (for example, step 6 when `+40700000301` isn't a Firebase test number).

- [ ] **Step 3: Release build launches**

Run: `./gradlew :app:assembleRelease`, then install it and launch. Expected: it reaches the sign-in screen without an R8 crash in `adb logcat -d | grep -i "FATAL\|SerializationException"`. The release build talks to production, so the DAS screens aren't reachable; the point is that R8 kept the new `@Serializable` classes. If it crashes, add keep rules under `app/src/main/keepRules/` and commit.

- [ ] **Step 4: Update app/AGENTS.md**

In the Layout block, replace "an empty DAS home" with the DAS incidents, and add `das/` lines: `Incidents.kt` (pure, tested on the JVM), `Incident*` screens, `Resolve*`. Commit: `docs(android): DAS screens in app/AGENTS.md`.

- [ ] **Step 5: Reset the data**

Run: `cd backend && uv run python scripts/seed.py --reset`.
