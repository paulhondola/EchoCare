# Demo showcase: live call, why red, DAS briefing, map, impact line

**Status:** draft for approval · 2026-11-14 · UniHack 8 ends 2026-11-15
**Scope:** `backend/` and `dashboard/`. Android, iOS and the home node are untouched (the home node is built by the other two team members).

## 1. Why

The judges see EchoCare for about three minutes. Today the strongest parts of the system, the AI talking to a senior and the fixed rules turning her words into a code, happen out of sight: the dashboard shows a transcript only after the call, inside an incident. These five additions put what the system already does on screen and in the judges' ears. None of them adds a new business rule.

| # | Feature | What the judges see or hear |
|---|---|---|
| 1 | Live call | The call to a judge's phone appears on the dashboard line by line, the alarm phrase lights up, the code flips to red |
| 2 | Why red | Each incident shows the chain from the senior's words to the code: answers, alarm phrase, severity × certainty |
| 3 | DAS briefing | The on-duty phone, when it picks up a hand-over, first hears a ~10 second spoken summary of who is calling and why |
| 4 | Map | Timișoara with every senior as a pin in her code's colour; live calls pulse; a red pulses red |
| 5 | Impact line | The landing page contrasts 15 volunteers calling 275 seniors a week with what EchoCare's lines can do |

## 2. Goals, non-goals, anti-goals

**Goals**
- Every feature works in the deployed staging stack and locally with seeded data.
- The live call shows a new line within about 1 second of it being stored.
- All user-facing text is Romanian; code and comments English (AGENTS.md).

**Non-goals**
- Server push of any kind (SSE, WebSocket). Decided: polling (§4).
- Geocoding through an outside service, or storing coordinates. Coordinates come from a fixed street table (§7).
- Showing live calls on Android or iOS.
- Linking a red to the medical record question that led to it: calls do not store which follow-up question was asked, and adding that is out of scope.

**Anti-goals** (would make this a failure even if it works)
- Anything that can drop or delay the live phone call on stage. The briefing (§6) is the only change on the call path; it must fall back to today's silent connect on any error.
- New rules or changes to how a code is decided. These features only display.
- Breaking installed apps: API changes only add (ADR-001 §2.3).

## 3. Approaches considered

**Getting live call data to the dashboard**

| | Approach | Trade-off |
|---|---|---|
| **A** | **Polling** (chosen) | A new `GET /calls/live` polled with the Shell's others; the open call's existing transcript endpoint polled every 1 s. ≤ 1 s delay, no new infrastructure, matches the spec's refetch model (G4) |
| B | Server-sent events | FastAPI 0.143 has `fastapi.sse`; auth works by reading the stream through `apiFetch`. About 1–2 h more, plus reconnect handling and a new failure mode on venue Wi-Fi. Nothing the judges see changes |
| C | WebSocket | Everything B costs plus a handshake; two-way traffic is not needed |

The user chose A.

**Map coordinates.** The senior called on stage is registered live by the medic during the demo (user's answer), so coordinates can't come only from seed data.

| | Approach | Trade-off |
|---|---|---|
| **A** | **Street table in the backend** (chosen) | A fixed table of ~40 Timișoara streets → approximate coordinates; `GET /seniors` adds the result. No migration, no write path, offline. Works for any senior on a listed street; the team registers the stage senior on one |
| B | Geocode the address with Nominatim at registration | Any address, but sends seniors' home addresses to a third party (against the trust sheet's story), needs the venue network, and adds a migration |
| C | DAS drops the pin on a map when accepting the senior | Exact, but a new write endpoint and an extra step in the middle of the demo |

*My call, chosen over a seed-only column after review:* A also covers the fictitious seed seniors, so `seed.py` needs no coordinates either.

**Briefing delivery:** Twilio's `<Number url=…>` already fetches `/voice/handoff-answered` when the on-duty phone picks up, before the two legs are bridged, and today returns empty TwiML. Returning a `<Say>` there is the whisper Twilio is built for (chosen). A separate pre-recorded audio file or an SMS to DAS were rejected: the first needs TTS generation and storage, the second is not heard on stage.

## 4. Live call (feature 1)

**Backend: `GET /calls/live`** (calls module, DAS only, 403 for others like the other DAS reads)

Returns the calls in `CallState.ringing` or `in_progress`, plus `handed_over` calls whose newest turn is under 90 seconds old (30 at first; raised in review: briefing, ring and DAS's first sentence can pass a minute), for seniors the DAS caller reaches, newest first. `queued` is excluded: nothing is happening yet. *Builder's call, settled in review:* `begin_handover` sets `ended_at` the moment the hand-over starts (`calls/ending.py`, `finish()`), but the DAS leg keeps adding `das` turns through `/voice/handoff-transcript`. A recency window on turns keeps the hand-over on screen with no migration and no write on the call path.

```json
[{ "id": "…", "senior_id": "…", "senior_name": "Maria Popescu", "trigger": "campaign",
   "state": "in_progress", "started_at": "…|null", "due_at": "…" }]
```

Usually 0–3 rows (3 calls at once is the scheduler's cap). Documented in `04-interfaces.md` §1 in the same change (contract rule).

**Transcript while live:** the existing `GET /calls/{id}/transcript` already returns turns stored so far (turns and answers commit as they arrive). No change, apart from checking it works for a call not yet ended (state not filtered); if it filters, relax that.

**Dashboard**
- `live.svelte.ts` adds `/calls/live` to the Shell's polls at 2 s, always (a tiny query, usually 0–3 rows). The other polls keep their intervals (incidents 15 s, seniors 120 s). When a call drops out of `/calls/live`, the Shell refreshes incidents and seniors at once, so a red reaches the banner, the siren and the map within ~2 s. *Builder's call, settled in review.*
- **Live strip:** when any call is live, a thin bar under the Cod Roșu banner position: `● Apel în desfășurare · Maria Popescu · campanie · 0:42`, one chip per call. Clicking a chip opens the live view.
- **Live view:** a slide-over in the same pattern as `IncidentDetails`, polling `GET /calls/{id}/transcript` every 1 s while open and the call is live, then stopping once `ended_at` is set. Reuses `CallTranscript.svelte` for the lines, with three additions:
  - new lines fade in and the list auto-scrolls to the newest;
  - a "typing" indicator on the speaker expected next while the call is live;
- the view keeps polling while the call is in `/calls/live` (so through the hand-over), not until `ended_at` is set;
  - the current code chip (from the newest report's severity, else the trigger's starting severity), which animates when it changes. A report whose `source` is `alarm_tier1` or `alarm_tier2` highlights the senior's words inside the matching senior turn (case- and diacritic-insensitive substring match; no match → highlight the whole turn). The words come from the report's `quote` when set, else from the «…» in `reason`: on a real call `add_report()` stores no quote and `begin_handover` writes the words into `reason` as „A spus: «…»”. *Builder's call, settled in review:* parse `reason` rather than change the call path.
- When the call ends red, the existing Cod Roșu banner and siren take over as today; the live view shows a link to the new incident.

## 5. Why red (feature 2)

A section at the top of `IncidentDetails`, titled **„De ce cod roșu?”**, built from the incident's deciding call: the call whose `final_severity` is red, else the newest call.

Rendered as a short vertical chain, each step one line, only steps that have data:

1. **Declanșator** — the trigger and, for a watch event, its kind (from `event`).
2. **Ce a spus** — the three answers (feeling, day, shelter) with value and a "neclar" badge when `clear` is false, each with its quote. Fetched from `GET /calls/{id}/transcript` (`answers`), which the incident detail does not include.
3. **Frază de alarmă** — any `alarm_tier1`/`alarm_tier2` report: the tier, its `reason` and the quoted words (`quote`, else the «…» in `reason`, as in §4).
4. **Severitate × certitudine** — a 3×3 grid (severity rows, certainty columns) with the call's cell lit, from `final_severity`/`final_certainty`; no certainty (unanswered) shows the row only.
5. **Rezultat** — the final code chip and `reason`, with the line „Modelul poate doar ridica nivelul, niciodată coborî” (G10).

Labels for `ReportSource` values go in `utils/labels.ts`. No backend change.

## 6. DAS briefing (feature 3)

`/voice/handoff-answered` keeps doing what it does (record the answer, take the incident), then returns `<Say>` with a briefing instead of empty TwiML. Built by a pure function, unit-tested:

> „Predare EchoCare. Doamna Maria Popescu, Calea Aradului 12, bloc A3. A spus: «mă doare în piept». Pe scurt: locuiește singură, are tensiune mare. Vă conectez.”

- Parts, in order, each skipped when missing: form of address and full name; street, number, block; the senior's words (the «…» in the incident `reason`, else the `reason` itself); the first sentence of the senior's latest summary `narrative` (`SummaryContent` in `seniors/schemas.py`). Target ≤ 25 words so the senior waits ~10 s.
- Uses the same `say()` voice as the rest of the call.
- Any exception while building it (database, missing summary) → log and return today's empty TwiML. The connect must never fail because of the briefing.
- Spec: one line in `04-interfaces.md` §4.4 step 5 and UC-07 noting the briefing.

## 7. Map (feature 4)

**Backend**
- A pure function in the seniors package, `approx_location(senior_id, street) -> (lat, lng) | None`, backed by a module-level dict of normalized Timișoara street names (diacritics and the „Strada/Calea/Bulevardul” prefix stripped, using the existing `normalize` from `status/alarms.py` or the same idea) to one point on each street. It covers every street in `scripts/seed.py` (19 today) plus ~20 main streets. Unknown street → `None`.
- So pins on the same street don't stack, add a small deterministic offset (up to ~80 m) derived from the senior's id. *ponytail:* street-level only; swap in stored coordinates if a pilot needs door-level accuracy.
- `GET /seniors` (list, `SeniorSummary`) gains optional `latitude` and `longitude`, filled from the function. Additive; in `04-interfaces.md` §1. No migration, no change to registration, nothing for erasure.
- Unit test with no database: a seed street resolves, prefix and diacritic variants resolve the same, an unknown street is `None`, two seniors on one street get different points.

**Dashboard**
- New route `/map`, sidebar entry **„Hartă”** next to „Seniori”.
- Leaflet (new dependency, `leaflet` + its CSS) with CARTO Dark Matter tiles to match the dark theme; OSM attribution shown. Centred on Timișoara.
- One circle marker per senior with coordinates, coloured by code (`rosu`, `galben`, `verde` tokens; no code → `fg-muted`). Seniors without coordinates are listed under the map as „Fără locație: N”.
- A red senior's marker pulses (CSS animation on the marker's element). A senior with a live call (from `/calls/live`) gets a ring that pulses in `link` colour, so a campaign visibly sweeps the city.
- Clicking a marker opens the existing `SeniorDetails` slide-over.
- Data from the Shell's existing seniors poll and `/calls/live`; no other reads.
- *Dropped in review:* the phone's last location as a second marker. It lives on the trigger event, which only `GET /incidents/{id}` returns, so it would need a contract change for little on stage.

## 8. Impact line (feature 5)

Static copy on `Landing.svelte`, a two-column contrast block under the hero:

| Azi | Cu EchoCare |
|---|---|
| 15 voluntari · 275 de seniori pe săptămână (Telefonul Vârstnicului, 2025) | 3 linii · până la 60 de apeluri pe oră, în timpul unui cod roșu |

60/hour = 3 calls at once × one call per ~3 minutes (06 §3). Numbers are hard-coded with their source in a comment; the landing page is shown signed out, so it reads nothing from the API.

## 9. Testing

- Backend: `GET /calls/live` (DAS sees live calls only, ended calls excluded, a hand-over within its 30 s window included, non-DAS refused); briefing builder (full data, missing summary, missing address, length cap); `handoff-answered` returns empty TwiML when the builder raises; the street table (§7) and the seniors list exposing coordinates. Run with the folder's usual `pytest`.
- Dashboard: unit tests for the alarm-quote highlighter and the deciding-call picker; `vp check`, `svelte-check`, build.
- In the browser against the local stack with seed data: map renders with pins, a mock or real call shows on the live strip, an incident shows „De ce cod roșu?”.
- The briefing is heard only on a real hand-over; test once on staging with the team's on-duty phone before the demo.

## 10. Ordering

Each feature ships on its own; suggested order by payoff per hour: 1 live call → 2 why red → 5 impact line → 3 briefing → 4 map. Backend pieces (§4, §6, §7) and dashboard pieces can be built in parallel once `GET /calls/live` and the coordinate fields are in `04-interfaces.md`.

**For the demo:** register the stage senior on a street from the table (§7), or she shows under „Fără locație”.

## 11. Left to the builder

- Exact component names and file split inside `dashboard/src/features/`.
- Animation details (fade, pulse timing), within spec 07's dark, square-cornered style.
- Exact Romanian wording of labels other than those quoted here.
- The street table's coordinates and which ~20 extra streets it lists.
- Whether the live view's 1 s poll uses `poll()` or a local timer.
