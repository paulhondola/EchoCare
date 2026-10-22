# DAS role in the Android app — design

Date: 2026-10-22. Status: approved in a grilling session, rounds 1–3, mockups approved.

## Intent

A DAS employee's phone is the on-duty phone: it takes the live hand-over call (D8) and has to show the incident behind it while they talk. Today the DAS role in the Android app lands on a placeholder that always says "Nu sunt incidente." ([HomeNav.kt](../../../android/app/src/main/java/ro/echocare/home/HomeNav.kt), `IncidentsRoute`). This change builds the DAS role as UC-11 and UC-12 describe it, against the backend that already serves it, and tests it end to end against the seeded local stack.

## Goals

- The DAS home lists red incidents, open and in progress, each with its status and who took it (UC-12).
- An incident page carries what a dispatcher needs to reach the senior: the reason, the senior's words, the address with access details, the location, call buttons, the calls and their transcripts (UC-11 step 1, UC-12).
- **Preiau** and **Rezolvat** work from the phone (UC-11 steps 2 and 4).
- A written e2e walkthrough against the seeded stack, plus JVM unit tests for the new logic.

## Non-goals

- **No push.** Red alerts and refresh pushes (04 §6) come later, as their own change across the app, the backend sender and the manifest. This change re-reads on the timer only.
- **No dashboard features.** Seniors, enrollment requests, campaigns, staff and on-duty stay on the dashboard.
- **No resolved incidents.** The app asks for `open,in_progress` only (04 §1). The 24-hour resolved list is the dashboard's.
- **No backend or contract change.** Everything below exists in the API today. `04-interfaces.md` and `backend/` are not touched.
- **No instrumented UI tests.** The repo has none beyond the template, and building that setup is a project of its own.

## Anti-goals

- A cue (sound, vibration) that fires only while the list is open and polling. Dispatchers would learn to trust it, and it would be silent with the phone in a pocket. The cue comes with push.
- Hiding the address or the call buttons behind tabs or taps.
- Telling "my" incidents apart by comparing display names. Names are not unique.

## Constraints

- Android only, one component per change (AGENTS.md "How changes ship"). One branch, one PR.
- New UI text is Romanian. Code and comments are English and cite the spec by ID.
- Old clients, new servers (ADR-001 §2.3): an unknown status, outcome, trigger, event type or speaker shows as the raw value or no label, never a crash. `ignoreUnknownKeys` is already on.
- Reuse what the app has: `Load`/`answer`/`after` and `Failure` ([Load.kt](../../../android/app/src/main/java/ro/echocare/home/Load.kt)), `RereadWhileShown`, `LoadBody`, `HomeScaffold`, `Message` ([Frame.kt](../../../android/app/src/main/java/ro/echocare/home/Frame.kt)), `refusalOf` ([enroll/Refusal.kt](../../../android/app/src/main/java/ro/echocare/enroll/Refusal.kt)), `formatPhone`, `Palette`, `Tone`, `SnButton`.
- Reads go through `answer { … }`. **Commands do not:** `failureOf` turns a 409 into `NoConnection`, so take and resolve read their refusal with `refusalOf`, which knows `already_done` and `wrong_state`.

## The API used

All under `/api`, all DAS-only, all live in the local OpenAPI.

| Call | Kotlin | Answers |
|---|---|---|
| `GET /incidents?status=open,in_progress` | `incidents(status)` | `List<IncidentSummary>`: `id`, `senior_full_name`, `senior_form_of_address`, `status`, `reason`, `opened_at`, `taken_by_name?`, `taken_at?`, `handover_answered` |
| `GET /incidents/{id}` | `incident(id)` | `IncidentDetail`: the summary's fields minus the senior names, plus `resolved_by_name?`, `resolved_at?`, `outcome?`, `note?`, `senior` (id, name, form of address, `phone_e164`, `phone_is_landline`, street, street_number, block, staircase, floor, apartment, intercom_code, key_holder, landmark), `caregivers` (display_name, phone_e164, relation?), `event?` (type, measured_at, latitude?, longitude?, location_accuracy_m?, located_at?), `calls` (id, trigger, attempt, state, started_at?, ended_at?, final_severity?, final_certainty?, reason?, summary?, handover_answered?, `reports` [source, severity, certainty?, reason, quote?, at], `turns` [speaker, kind, content, at]) |
| `POST /incidents/{id}/take` | `take(id)` | `IncidentSummary`. 409 `{"detail":{"reason":"already_done","taken_by_name":"…"}}` when someone else holds it, 409 `wrong_state` when resolved |
| `POST /incidents/{id}/resolve` | `resolve(id, body)` | Body `{outcome, note}`: both required; `note` 1–1000 characters; `outcome` one of `senior_ok`, `team_sent`, `called_112`, `not_reached`, `false_alarm`. Answers `IncidentSummary`. 409 `wrong_state` while still open, `already_done` when resolved by someone else or with another outcome |

The data classes keep only the fields the app reads, with enum-like fields as strings, as `Api.kt` already does.

## Decided

### Screens and navigation

`IncidentsRoute` stays the DAS home. Two routes are added: `IncidentRoute(id)` and `ResolveRoute(id)`. Back from the incident returns to the list. A successful resolve pops back to the list.

The approved mockup lives at `.superpowers/brainstorm/45833-1792699504/content/das-screens.html` (git-ignored, local only).

### The list (home)

- Two sections, **Deschise** then **În lucru**, each with its count. Inside a section, the longest wait comes first: open by `opened_at` oldest first, in progress by `taken_at` (falling back to `opened_at`) oldest first. This is the dashboard's `columns()` in [utils/incidents.ts](../../../dashboard/src/utils/incidents.ts).
- A card shows the senior's full name, the reason, how long ago it opened ("acum 49 min", "acum 2 h 6 min", the date past a day, as the dashboard's `since()`), a status chip, and a hand-over marker as the dashboard's card has it: "Transferat la DAS" when `handover_answered` is true, "Nepreluat" when false. Its bar takes the status's colour, as the dashboard's card: red open, yellow in progress. `false` also covers an incident that never had a hand-over (every red from the mock card ends `completed`); this matches the dashboard, and telling the two apart would need a backend field. Open: red chip "Deschis". In progress: yellow chip "În lucru · preluat de {taken_by_name}" ("un dispecer" when the name is missing), as the dashboard.
- Empty: the existing "Nu sunt incidente." text.
- Tapping a card opens the incident.

### The incident page

One scrolling page, no tabs, in this order:

1. **Status and reason.** Status chip in the status's colour (red Deschis · acum X / yellow În lucru · preluat de {name} / green Rezolvat), an "Apel în curs" badge when any call is `ringing` or `in_progress`, the incident's reason, then the senior's words: the `quote` of the latest red report across the calls, in quotation marks, left out when there is none.
2. **Adresă și acces.** Street and number, then each access detail present (bloc, scară, etaj, ap., interfon, reper, cheie), and **Deschide în Hărți**.
3. **Telefon.** The senior first, with a landline or mobile badge, then each caregiver with their relation. Each has a **Sună** button. Numbers are shown with `formatPhone`.
4. **Eveniment**, only when `event` is present: type label, when it was measured, coordinates and accuracy when present.
5. **Apeluri.** Every call of the incident, newest first. The newest is expanded and the older ones collapse to one line (trigger, attempt, final severity) that expands on tap. An expanded call shows its turns as speaker label (*Senior*, *Sistem AI*, *Sistem*), clock time and text, with each status report placed inline at its time as "Cod Roșu · semnalat — {reason}". Under the turns, when the call's own `handover_answered` is not null: "Transferat la telefonul de serviciu DAS" (true) or "Transferul nu a fost preluat" (false), as the dashboard's "Predare audio" line; null means no hand-over was tried and shows nothing *(builder-check call)*. With no calls: "Niciun apel înregistrat pentru acest incident."

A pinned bottom bar holds the one action the status allows:
- `open`: **Preiau**.
- `in_progress`: **Rezolvă cazul**, blue link style as the dashboard's card, for any DAS employee, not only the one who took it. Green stays for **Trimite** and the resolved state.
- `resolved`: no button. This can happen when someone resolved it while the page was open; the next list read drops it.

### Phone and Maps

- **Sună** opens the dialer with the number filled in (`Intent.ACTION_DIAL`, `tel:`). No `CALL_PHONE` permission.
- **Deschide în Hărți** opens a `geo:` URI: `geo:{lat},{lng}?q={lat},{lng}` when the event has coordinates, otherwise `geo:0,0?q={street} {number}, Timișoara` built from the address. Seniors have no city field and the service is DAS Timișoara, so the city is a constant *(builder-check call; a city field would replace it)*. When nothing handles the intent, it does nothing; no crash.
- Times show in the device's time zone. The API sends UTC *(builder-check call)*.

### Preiau

Posts `take`. On success the page re-reads. On a refusal it shows a message and re-reads, because a 409 means the screen is stale:
- `already_done` with `taken_by_name`: "Preluat deja de {name}."
- `wrong_state`: "Incidentul s-a schimbat între timp."
- Anything else maps as for a read (no connection, not allowed, signed out, not found), with the dashboard's wording from [commands.ts](../../../dashboard/src/features/incidents/commands.ts): "Nu am putut trimite. Încercați din nou.", "Nu aveți dreptul să faceți asta.", "Incidentul nu mai există."

`refusalOf` returns `AlreadyDone` with no name today. It has to carry `taken_by_name` for this; see "Left to the builder".

### Rezolvare caz

A full-screen step: the five outcomes as radio buttons in the dashboard's order and wording (Senior OK, Echipaj trimis, Apelat 112, Nu a răspuns, Alarmă falsă), then a required **Notă** with a counter up to 1000 characters. **Trimite** stays disabled until an outcome is picked and the trimmed note is not empty. Success returns to the list. A refusal shows the message as for Preiau and stays on the step, keeping what was typed. `already_done` here reads "Incidentul a fost deja rezolvat." A 422 should not happen past the form's own checks; if it does, it shows the generic send message.

### Re-reading

- The list and the incident page each re-read with `RereadWhileShown` every `REREAD_SECONDS`, through `Load`, so a lost connection keeps the last data under the offline banner.
- The resolve step reads nothing. It is its own route, so the incident page's re-read stops while it is open, and a background read cannot wipe a half-typed note.
- A `Failure` that ends the session goes to `onSessionEnd`, as on the other homes.

### Romanian text

New strings, matching the dashboard where it has them: Deschise, În lucru, Deschis, Preluat de %s, Rezolvat, acum câteva secunde / acum %d min / acum %d h %d min, Transferat la DAS, Nepreluat, Transferat la telefonul de serviciu DAS, Transferul nu a fost preluat, Apel în curs, Adresă și acces, Bloc, Scară, Etaj, Ap., Interfon, Reper, Cheie, Deschide în Hărți, Telefon, Fix, Mobil, Sună, Eveniment, Tip, Măsurat la, Locație, Apeluri, Senior, Sistem AI, Sistem, semnalat, Niciun apel înregistrat pentru acest incident., Preiau, Rezolvare caz, Rezultat, Notă, Trimite, the five outcome labels, the refusal messages above. Labels for the triggers (Campanie, Ceas, Cerere „Sunați-mă”, Apel de bun venit) and event types (Buton SOS, Cădere detectată, Puls ridicat în repaus, Inactivitate) are copied from [IncidentDetails.svelte](../../../dashboard/src/features/incidents/IncidentDetails.svelte).

### Delivery

One branch, one PR, three commits, each leaving a working app:

1. `Api.kt` incident reads, the data classes, `IncidentsViewModel`, the list.
2. The incident page, Maps and dial intents.
3. Preiau, Rezolvare caz, refusal handling.

## Testing

### Unit tests (JVM, `app/src/test`)

In the style of `LoadTest` and `RoutesTest`. Cover what has branches:
- List sorting and sectioning, including the `taken_at` fallback.
- The "acum …" formatting at its boundaries (under a minute, 59 min, 1 h 0 min, a day).
- Which action a status allows.
- Picking the senior's words: the latest red report's quote across calls, none when absent.
- Call ordering and which call starts expanded.
- The Maps URI with coordinates and from the address.
- Reading the take refusal: `already_done` with and without `taken_by_name`, `wrong_state`, a non-JSON body.
- The resolve form's enable rule: no outcome, blank note, a note over 1000 characters.
- `ApiTest`: decoding a captured `GET /incidents/{id}` body with an unknown extra field.

### E2E walkthrough (manual, written into the PR)

Setup: `docker compose up --watch`, `cd backend && uv run python scripts/seed.py --reset`, `echocare.apiUrl=http://10.0.2.2:8000` in `local.properties`, then `adb shell pm grant ro.echocare android.permission.ACCESS_LOCAL_NETWORK` after each fresh install. Sign in on the emulator as **DAS Test** (`+40700000001`).

1. The list shows 4 under Deschise (Aurelia Marinescu, Dumitru Pop, Ion Dumitrescu, Teodor Crișan, in that order) and 4 under În lucru, with Gavril Szabó "Preluat de Cristian Pavel".
2. Open Dumitru Pop: the reason, the quote „Mă strânge în piept și nu pot respira bine.”, Strada Bucovinei 27 with bloc H4, scara A, etaj 5, ap. 31, interfon 31, Simona Pop · fiică, the SOS event with ±14 m, and the watch call's transcript with Cod Galben then Cod Roșu inline.
3. Sună on the senior opens the dialer with 0700 000 113. Deschide în Hărți opens Maps at 45.7489, 21.2087.
4. Preiau: the chip becomes "Preluat de DAS Test", the button becomes Rezolvat, and the dashboard shows it in progress within a few seconds.
5. Rezolvat → Echipaj trimis plus a note → Trimite: back on the list, Dumitru Pop is gone, and the dashboard shows it resolved with the note.
6. Conflict: on the dashboard, signed in as **Cristian Pavel** (`+40700000301`), take Ion Dumitrescu. On the phone, with Ion Dumitrescu's page open, press Preiau: "Preluat deja de Cristian Pavel." and the page re-reads. If `+40700000301` is not a Firebase test number, skip this step; the unit test covers the refusal, and step 1 already shows another dispatcher's hold.
7. Stop the API container with the list open: the offline banner appears over the last data. Start it again and the banner clears on the next read.
8. Reset with `seed.py --reset`.

## Left to the builder

- How `taken_by_name` gets out of the refusal body: a field on `Refusal.AlreadyDone`, or a small parser beside it. Keep the existing enroll callers working.
- The Kotlin file and class layout under `ro.echocare` (for example a new `das` package or files in `home`).
- Exact typography, spacing and chip styling within the existing `Palette`/`Tone` and components. Avoid `FgSubtle` for text a dispatcher must read: it was flagged as low contrast.
- Whether the collapsed-call expand state survives configuration changes.
