# Demo showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the live AI call, the reasoning behind a red, a spoken DAS briefing, a Timișoara map and an impact line in front of the UniHack judges.

**Architecture:** Two additive API reads (`GET /calls/live`, coordinates on `GET /seniors`) and one change on the hand-over callback (a `<Say>` whisper). Everything else is the Svelte dashboard reading data the backend already stores. Polling, not push.

**Tech Stack:** FastAPI + SQLAlchemy async + pytest (backend, `uv`); Svelte 5 + SvelteKit 3 + Tailwind v4 + Vite+ (`vp`) (dashboard); Leaflet 1.9.4 (new).

**Spec:** `docs/superpowers/specs/2026-11-14-demo-showcase-design.md`

Work in the worktree `/Users/paulhondola/Developer/EchoCare-demo-showcase`, branch `demo-showcase`. Backend commands from `backend/`, dashboard commands from `dashboard/`.

## Global Constraints

- User-facing text in Romanian; code, comments and docs in English (AGENTS.md).
- API changes only add: new response fields optional, nothing renamed or dropped (ADR-001 §2.3).
- Contract changes move together: `docs/specs/echocare/04-interfaces.md`, the backend and `dashboard/src/services/api.ts` in the same commit (Android does not call the new reads).
- No migration. No new rule about how a code is decided.
- The hand-over must connect even when the briefing fails: on any exception, today's empty TwiML.
- Dashboard styling from the `styles.css` tokens (`rosu`, `galben`, `verde`, `link`, `fg-muted`, `line`, `card`), `sn-btn` buttons, `ui/Icon.svelte`, square corners; full class names in quotes (dashboard/AGENTS.md).
- Backend: import a name from the module that defines it; only a table's owner writes it; `uv run lint-imports` passes. `seniors` may import `status` (below it); `voice` may import `seniors`.
- Commit with hooks on; never `--no-verify`.

## Review Focus

1. **A call that ends while its live view is open** — the view must stop polling once the call leaves `/calls/live` and show the final code, not keep spinning. Test: Task 2 Step 1 `liveCallDone`.
2. **A red with no «…» in `reason`** (alarm via key 9, tier 2 silence) — highlight falls back to the whole senior turn, the why-red card and the briefing skip the quote, nothing throws. Tests: Task 2 `alarmWords` null case; Task 5 `test_briefing_without_quote`.
3. **Two seniors on one street, or an unknown street** — distinct pins; unknown street gives no coordinates and the senior is listed under „Fără locație”. Tests: Task 6.
4. **A test call** (`trigger` `test`, from `place_call.py`) — never shown as live. Test: Task 1 `test_test_calls_are_not_live`.
5. **A senior with no summary or no address at hand-over** — the briefing still speaks what it has. Test: Task 5 `test_briefing_with_nothing_but_a_name`.

---

### Task 1: `GET /calls/live`

**Files:**
- Modify: `backend/app/calls/schemas.py`, `backend/app/calls/service.py`, `backend/app/calls/router.py`
- Modify: `docs/specs/echocare/04-interfaces.md` (new row after the Transcript row, §1)
- Modify: `dashboard/src/services/api.ts`
- Test: `backend/tests/calls/test_live_calls.py`

**Interfaces:**
- Produces (backend): `LiveCall(BaseModel)` with `id: uuid.UUID, senior_id: uuid.UUID, senior_name: str, trigger: str, state: str, starting_severity: str, started_at: datetime | None, due_at: datetime`; `async def live_calls(session: AsyncSession) -> list[LiveCall]`; route `GET /calls/live` guarded by `require_roles(Role.das)` (as `GET /incidents`).
- Produces (dashboard): `export interface LiveCall` mirroring the above (ids and dates as `string`); `export async function fetchLiveCalls(signal?: AbortSignal): Promise<LiveCall[]>`.

- [ ] **Step 1: Write the failing tests** in `test_live_calls.py`, using `add_user`, `add_active_senior`, `client`, `db` from `tests/conftest.py` and `signed_in(token)` = `{"Authorization": f"Bearer {token}"}` (the token is the phone number):
  - `test_ringing_and_in_progress_calls_are_live` — calls in `ringing`, `in_progress`, `queued`, `completed`; DAS gets exactly the first two, newest `due_at` first, with `senior_name` = the senior's `full_name`.
  - `test_a_hand_over_stays_live_while_das_talks` — a `handed_over` call with `ended_at` set and a `CallTurn` at now − 10 s is live; one whose newest turn is at now − 40 s is not; one with no turns is not.
  - `test_test_calls_are_not_live` — `trigger=CallTrigger.test`, `in_progress` → absent.
  - `test_only_das_sees_live_calls` — a medic gets 403.
- [ ] **Step 2: Run** `uv run pytest tests/calls/test_live_calls.py -v` → FAIL (404 on the route).
- [ ] **Step 3: Implement** `LiveCall` in `calls/schemas.py`; `live_calls(session)` in `calls/service.py`: one select of `Call` joined to `Senior`, where `trigger != test` and (`state in (ringing, in_progress)` or (`state == handed_over` and the max `CallTurn.at` for the call `>= now - 30 s`)), ordered by `due_at desc`. Name the window `HANDOVER_LIVE = timedelta(seconds=30)` with a comment citing design §4. Route in `calls/router.py` above `/calls/{call_id}/transcript` so `live` is not parsed as a UUID.
- [ ] **Step 4: Run** `uv run pytest tests/calls -v` → PASS; `uv run ruff check . && uv run ruff format --check . && uv run lint-imports` → clean.
- [ ] **Step 5: Contract.** In `04-interfaces.md` §1 add a row `| Live calls | \`GET /calls/live\` | DAS | …fields above…; ringing or in progress, plus a hand-over while its newest turn is under 30 seconds old; test calls left out (design 2026-11-14 §4) |`. In `api.ts` add `LiveCall` and `fetchLiveCalls` next to `fetchTranscript`, same `apiFetch` / `refused` pattern.
- [ ] **Step 6: Run** `npx vp check && npx svelte-check --tsgo --fail-on-warnings` from `dashboard/` → clean.
- [ ] **Step 7: Commit** `feat: GET /calls/live for the dashboard's live call view`.

### Task 2: Live strip and live view (dashboard)

**Files:**
- Create: `dashboard/src/utils/live.ts`, `dashboard/src/utils/live.test.ts`
- Create: `dashboard/src/features/calls/LiveStrip.svelte`, `dashboard/src/features/calls/LiveCallView.svelte`
- Modify: `dashboard/src/features/shell/live.svelte.ts`, `dashboard/src/features/shell/Shell.svelte`, `dashboard/src/features/calls/CallTranscript.svelte`

**Interfaces:**
- Consumes: `fetchLiveCalls`, `LiveCall` (Task 1); `fetchTranscript`, `IncidentCall` (existing).
- Produces (`utils/live.ts`, used by Task 3):
  - `alarmWords(report: { source: string; quote: string | null; reason: string }): string | null` — `quote` if set, else the text between `«` and `»` in `reason`, else null. Only for `source` `alarm_tier1` / `alarm_tier2`; other sources → null.
  - `highlight(turn: string, words: string): [string, string, string] | null` — before / match / after, matched case- and diacritic-insensitively (NFD + strip combining marks for comparison, slice the original string); null when absent.
  - `currentCode(call: IncidentCall, starting: "green" | "yellow" | "red"): "green" | "yellow" | "red"` — `final_severity` if set, else newest report's severity, else `starting`.
  - `liveCallDone(id: string, live: LiveCall[]): boolean` — true when `id` is not in `live`.
- Produces (`Live` class): `liveCalls = poll(fetchLiveCalls, LIVE_MS, describe(...))` with `LIVE_MS = 2_000`; `liveCall = $state<string | null>(null)` (the open view's call id).

- [ ] **Step 1: Write the failing tests** in `live.test.ts` (vitest, as the other `utils/*.test.ts`):
  - `alarmWords` → `"mă doare în piept"` from `{source:"alarm_tier1", quote:null, reason:"A spus: «mă doare în piept»"}`; quote wins over reason; `null` for `reason:"A cerut un operator (tasta 9)"`; `null` for `source:"rules"`.
  - `highlight("Mă doare în piept tare", "ma doare in piept")` → `["", "Mă doare în piept", " tare"]`; `highlight("bine", "piept")` → `null`.
  - `currentCode` with `final_severity:"red"` → red; no final, reports `[yellow, red]` → red; neither → the starting value.
  - `liveCallDone("a", [{id:"a",…}])` → false; `liveCallDone("a", [])` → true.
- [ ] **Step 2: Run** `npx vp test src/utils/live.test.ts` → FAIL (module missing).
- [ ] **Step 3: Implement** `utils/live.ts`.
- [ ] **Step 4: Run** `npx vp test src/utils/live.test.ts` → PASS.
- [ ] **Step 5: Wire the poll.** Add `liveCalls` and `liveCall` to `Live`. In `Shell.svelte`, an `$effect` that remembers the previous live ids and, when one disappears, calls `live.incidents.reload()` and `live.seniors.reload()` (design §4: a red reaches banner, siren, map within ~2 s).
- [ ] **Step 6: `LiveStrip.svelte`** — rendered in `Shell.svelte` right after the `RedAlert` block, only when `liveCalls` has rows: one chip per call, `● Apel în desfășurare · {senior_name} · {TRIGGERS[trigger]} · {m:ss since started_at}` (dot pulses in `link`), click sets `live.liveCall = id`.
- [ ] **Step 7: `LiveCallView.svelte`** — slide-over in `IncidentDetails`' pattern, mounted from `Shell.svelte` when `live.liveCall` is set. Polls `fetchTranscript(id)` every 1 s with a local timer while `!liveCallDone(id, liveCalls)`, then one last read and stop. Header: senior name, trigger, the `currentCode` chip (starting value: the live call's `starting_severity`) animating on change. Body: `CallTranscript`. When done and the code is red, a link „Deschide incidentul” that closes the view and sets `live.dossier` to the senior's open incident (match by `senior_full_name` in `live.incidents`).
- [ ] **Step 8: `CallTranscript.svelte` additions**, behind a new optional prop `live = false`: new turns fade in; auto-scroll to the newest; a three-dot typing indicator under the last turn while `live`; for each senior turn, if any report's `alarmWords` is found by `highlight`, wrap the match in `<mark class="bg-rosu/25 text-fg">`, else if the alarm report exists and nothing matches, mark the newest senior turn before the report's `at` whole. Existing callers pass nothing and look as before.
- [ ] **Step 9: Run** `npm run check && npx svelte-check --tsgo --fail-on-warnings && npx vp test && npm run build` → all clean.
- [ ] **Step 10: Browser check** against the local stack (`docker compose up --watch db api dashboard`, seed with `uv run python scripts/seed.py --reset`): with no live call no strip; insert an `in_progress` call for a seeded senior and add turns with `psql` or the senior's mock-call card, see the strip, open the view, see lines appear.
- [ ] **Step 11: Commit** `feat(dashboard): live call strip and view`.

### Task 3: „De ce cod roșu?” (dashboard)

**Files:**
- Create: `dashboard/src/features/incidents/WhyRed.svelte`
- Modify: `dashboard/src/features/incidents/IncidentDetails.svelte` (top of the `access` tab, the dossier's first tab), `dashboard/src/utils/labels.ts`, `dashboard/src/utils/incidents.ts`, `dashboard/src/utils/incidents.test.ts`

**Interfaces:**
- Consumes: `alarmWords` (Task 2); `fetchTranscript` (existing; its `answers` field must be added to the `IncidentCall`-based type if missing: `answers: { field: string; value: string; clear: boolean; quote: string; at: string }[]`).
- Produces: `decidingCall<T extends { final_severity: string | null; started_at: string | null }>(calls: T[]): T | null` in `utils/incidents.ts`; `REPORT_SOURCES: Record<string, string>` in `labels.ts` (`rules` „Reguli fixe”, `raise_concern` „Modelul a ridicat nivelul”, `alarm_tier1` „Frază de alarmă, nivel 1”, `alarm_tier2` „Frază de alarmă, nivel 2”, `request_human` „A cerut un operator”, `trigger` „Declanșator”, `unanswered` „Fără răspuns”).

- [ ] **Step 1: Failing tests** in `incidents.test.ts`: `decidingCall` picks the red call over a newer green one; with no red, the newest by `started_at`; `[]` → null.
- [ ] **Step 2: Run** `npx vp test src/utils/incidents.test.ts` → FAIL.
- [ ] **Step 3: Implement** `decidingCall` and `REPORT_SOURCES`.
- [ ] **Step 4: Run** the same → PASS.
- [ ] **Step 5: `WhyRed.svelte`** props `{ detail: IncidentDetail }`: picks `decidingCall(detail.calls)`, fetches its transcript for `answers`, renders the five steps of design §5 (Declanșator from `detail.event`, Ce a spus with a „neclar” badge when `!clear`, Frază de alarmă via `alarmWords`, the 3×3 Severitate × Certitudine grid with the call's cell lit, Rezultat with „Modelul poate doar ridica nivelul, niciodată coborî”). Steps without data are not rendered. Fetch failure shows the steps it has.
- [ ] **Step 6: Mount** it at the top of the `access` tab in `IncidentDetails.svelte`.
- [ ] **Step 7: Run** `npm run check && npx svelte-check --tsgo --fail-on-warnings && npx vp test && npm run build`; open a seeded red incident in the browser and see the card.
- [ ] **Step 8: Commit** `feat(dashboard): why-red card on the incident`.

### Task 4: Impact line (dashboard)

**Files:** Modify `dashboard/src/features/landing/Landing.svelte` (a new block between the hero `</section>` at ~line 208 and the `does-title` section).

- [ ] **Step 1: Add** a two-column contrast block. Copy, verbatim:
  - Left, label „Azi”: „15 voluntari · 275 de seniori pe săptămână” and a small source line „Telefonul Vârstnicului, 2025”.
  - Right, label „Cu EchoCare”: „3 linii · până la 60 de apeluri pe oră” and „în timpul unui cod roșu”.
  - Comment above: `<!-- 60/h = 3 calls at once × one call per ~3 minutes (06 §3); 275/15 from the hackathon brief -->`.
  Stacks to one column under `md`.
- [ ] **Step 2: Run** `npm run check && npx svelte-check --tsgo --fail-on-warnings && npm run build`; signed out in the browser, see it at desktop and 375 px width.
- [ ] **Step 3: Commit** `feat(dashboard): impact line on the landing page`.

### Task 5: Spoken briefing on hand-over (backend)

**Files:**
- Modify: `backend/app/voice/dialogue.py` (pure builder), `backend/app/voice/service.py` (read), `backend/app/voice/router.py` (`handoff_answered`)
- Modify: `docs/specs/echocare/04-interfaces.md` (the „Hand-over answered” row, §4.4 table)
- Test: `backend/tests/voice/test_briefing.py` (pure), `backend/tests/voice/test_handover.py` (route)

**Interfaces:**
- Produces: `def briefing(form_of_address: str, full_name: str, address: str | None, reason: str | None, narrative: str | None) -> str` in `dialogue.py`; `async def handover_briefing(session: AsyncSession, call_id: uuid.UUID) -> str | None` in `voice/service.py` (None when the call is unknown).

Briefing shape, parts skipped when missing, joined with single spaces:
`„Predare EchoCare.”` · `„{form_of_address}, {full_name}”` + `„, {address}.”` or `„.”` · `„A spus: «{words}».”` where words = the «…» in `reason`, else omitted · `„Pe scurt: {first sentence of narrative}”` (split on the first `.`, `!` or `?`) · `„Vă conectez.”`. Capitalize nothing beyond what the inputs carry.

- [ ] **Step 1: Failing pure tests** in `test_briefing.py` (no database):
  - `test_briefing_in_full` — `briefing("doamna Maria", "Maria Popescu", "Calea Aradului 12, bloc A3", "A spus: «mă doare în piept»", "Locuiește singură. Are tensiune mare.")` == `"Predare EchoCare. doamna Maria, Maria Popescu, Calea Aradului 12, bloc A3. A spus: «mă doare în piept». Pe scurt: Locuiește singură. Vă conectez."`
  - `test_briefing_without_quote` — `reason="A cerut un operator (tasta 9)"` → no „A spus” part.
  - `test_briefing_with_nothing_but_a_name` — address, reason, narrative all None → `"Predare EchoCare. doamna Maria, Maria Popescu. Vă conectez."`
  - `test_briefing_stays_short` — a 600-char narrative of one sentence → the result has at most 45 words (cut the narrative's sentence to 20 words).
- [ ] **Step 2: Run** `uv run pytest tests/voice/test_briefing.py -v` → FAIL.
- [ ] **Step 3: Implement** `briefing` in `dialogue.py`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Failing route tests** in `test_handover.py`, reusing `handed_over`, `on_duty_das`, `callback`, `twiml`:
  - Change `test_answering_takes_the_incident`'s `assert len(root) == 0` to: one `<Say>` whose text starts with `"Predare EchoCare."`.
  - `test_a_failing_briefing_still_connects` — monkeypatch `app.voice.router.handover_briefing` to raise `RuntimeError`; response is empty TwiML (`len(root) == 0`) and the incident is still taken.
- [ ] **Step 6: Run** `uv run pytest tests/voice/test_handover.py -v` → the two FAIL.
- [ ] **Step 7: Implement** `handover_briefing` (load `Call` + `Senior`; address = street, number, block from the senior; `reason` = `call.reason`; narrative via `latest_summary` + `read_content` from `app.seniors.service`). In `handoff_answered`, after the existing commit block, `try:` build it and return `twiml(say(text))`; `except Exception:` log `"hand-over briefing for call %s failed"` with `log.exception` and return `twiml("")`. Never log the briefing text (health data).
- [ ] **Step 8: Run** `uv run pytest tests/voice -v && uv run ruff check . && uv run ruff format --check . && uv run lint-imports` → clean.
- [ ] **Step 9: Contract.** Replace „Nothing to say; connect.” in the Hand-over answered row with „Says a short briefing (who, address, the senior's words, the summary's first sentence) to the employee, then connects; any failure building it connects silently (design 2026-11-14 §6).”
- [ ] **Step 10: Commit** `feat: spoken briefing to DAS before a hand-over connects`.

### Task 6: Approximate senior locations (backend)

**Files:**
- Create: `backend/app/seniors/places.py`
- Modify: `backend/app/seniors/schemas.py` (`SeniorSummary`), `backend/app/seniors/service.py` (`senior_summaries`, ~line 122)
- Modify: `docs/specs/echocare/04-interfaces.md` (the Seniors row, §1), `dashboard/src/services/api.ts` (`SeniorSummary`)
- Test: `backend/tests/seniors/test_places.py`, one case in `backend/tests/seniors/test_seniors.py`

**Interfaces:**
- Produces: `def approx_location(senior_id: uuid.UUID, street: str | None) -> tuple[float, float] | None` in `seniors/places.py`; `SeniorSummary.latitude: float | None = None`, `SeniorSummary.longitude: float | None = None`; same two optional fields on the dashboard's `SeniorSummary`.

- [ ] **Step 1: Failing tests** in `test_places.py` (no database):
  - `test_a_seed_street_resolves` — every street in `scripts/seed.py` (Bulevardul Cetății, Bulevardul Eroilor de la Tisa, Bulevardul Take Ionescu, Calea Aradului, Calea Buziașului, Calea Girocului, Calea Lipovei, Calea Martirilor, Calea Șagului, Strada Alba Iulia, Strada Arieș, Strada Bucovinei, Strada Cluj, Strada Gheorghe Lazăr, Strada Lipovei, Strada Memorandumului, Strada Mărășești, Strada Pestalozzi, Strada Take Ionescu) returns a point inside the box lat 45.70–45.81, lng 21.15–21.30.
  - `test_spelling_variants_match` — `"calea aradului"`, `"Calea Aradului"`, `"Aradului"` and `"Str. Mărășești"` / `"Marasesti"` resolve to points within 100 m of each other for the same senior id.
  - `test_unknown_street_is_none` — `"Strada Inexistentă"` and `None` → None.
  - `test_neighbours_do_not_stack` — two different uuids on Calea Aradului → different points, each within 120 m of the street's base point.
- [ ] **Step 2: Run** `uv run pytest tests/seniors/test_places.py -v` → FAIL.
- [ ] **Step 3: Implement** `places.py`: a `STREETS: dict[str, tuple[float, float]]` keyed by normalized name (via `app.status.alarms.normalize`, then strip a leading `strada|str|calea|bulevardul|bd|bulevard|piata|aleea`), covering the 19 seed streets plus ~20 main Timișoara streets the builder picks; the offset: two bytes of `senior_id.bytes` each mapped to ±0.0007° (~80 m). `# ponytail: street-level only; stored coordinates if a pilot needs the door.`
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Wire.** Add the two fields to `SeniorSummary`; in `senior_summaries` add `"latitude", "longitude"` to the excluded `fields` set (the `Senior` row has no such attributes) and pass `latitude=…, longitude=…` from `approx_location(senior.id, senior.street)`. Add `test_the_list_carries_an_approximate_location` to `test_seniors.py`: a senior on Calea Aradului has both fields set in `GET /seniors`; one with no street has both null.
- [ ] **Step 6: Run** `uv run pytest tests/seniors -v && uv run ruff check . && uv run ruff format --check . && uv run lint-imports` → clean.
- [ ] **Step 7: Contract.** In the Seniors row of `04-interfaces.md` §1 add: „`latitude` and `longitude`, an approximate point on the senior's street from a fixed table of Timișoara streets, for the dashboard's map; null when the street is not in the table (design 2026-11-14 §7).” Add the fields to `SeniorSummary` in `api.ts`. Run `npx vp check` in `dashboard/`.
- [ ] **Step 8: Commit** `feat: approximate senior locations on GET /seniors`.

### Task 7: Map page (dashboard)

**Files:**
- Create: `dashboard/src/routes/map/+page.svelte`, `dashboard/src/features/map/SeniorMap.svelte`
- Modify: `dashboard/src/features/shell/Sidebar.svelte` (item after „Monitorizare seniori”: `href: "/map"`, label „Hartă”, a Lucide map icon via `ui/Icon.svelte`), `dashboard/package.json` + `package-lock.json`, `dashboard/AGENTS.md` (layout tree: `map/` route and feature)

**Interfaces:**
- Consumes: `live.seniors` (with Task 6's `latitude`/`longitude`), `live.liveCalls` (Task 2), `SeniorDetails.svelte` (existing slide-over, props `senior`, `onClose`, `onErased`).

- [ ] **Step 1: Install** `npm install leaflet@1.9.4 && npm install -D @types/leaflet@1.9.22`.
- [ ] **Step 2: `SeniorMap.svelte`** — creates the Leaflet map in `onMount` on a `bind:this` div (client-only; the app is SPA, `ssr = false`), centre `[45.7537, 21.2257]`, zoom 13, tiles `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png` with attribution „© OpenStreetMap, © CARTO”. Import `leaflet/dist/leaflet.css`. One `L.circleMarker` per senior with coordinates, colour from the code token (`rosu` / `galben` / `verde`, `fg-muted` for none; read the CSS variables with `getComputedStyle`), updated in an `$effect` when `live.seniors` changes (update existing markers by id, don't rebuild the map). A red marker gets a `className` with a CSS pulse; a senior whose id is in `liveCalls` gets a second pulsing ring in `link`. Marker click → opens `SeniorDetails` for that senior. Under the map: „Fără locație: N” when any senior lacks coordinates. Destroy the map in the `onMount` cleanup.
- [ ] **Step 3: Route** `routes/map/+page.svelte` renders `PageHeader` („Hartă”) and `SeniorMap`, as the other pages do.
- [ ] **Step 4: Run** `npm run check && npx svelte-check --tsgo --fail-on-warnings && npx vp test && npm run build` → clean.
- [ ] **Step 5: Browser check** with seed data: pins over Timișoara in code colours, a red one pulsing, clicking opens the senior; with a live call inserted (Task 2 Step 10) its pin rings; no console errors.
- [ ] **Step 6: Commit** `feat(dashboard): Timișoara map of seniors`.

### Task 8: Whole-branch check

- [ ] **Step 1:** From `backend/`: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run lint-imports` → all pass.
- [ ] **Step 2:** From `dashboard/`: `npm run check && npx svelte-check --tsgo --fail-on-warnings && npx vp test && npm run build` → all pass.
- [ ] **Step 3:** Browser walk-through on the local stack: landing (impact line), board → strip → live view → incident with „De ce cod roșu?” → map. Screenshot each for the pitch deck.
- [ ] **Step 4:** Note for the team in the PR description: register the stage senior on a street from `places.py`; test the briefing once on staging with the on-duty phone before the demo (needs a real hand-over).
