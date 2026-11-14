# Campaigns and mock calls: design

**Date:** 2026-10-17
**Status:** Settled in three grilling rounds on 2026-10-17 (Q1 to Q19); awaiting approval
**Classification:** Architectural (changes the `04-interfaces.md` contract)
**Scope:** `backend/app/`, `backend/tests/`, `backend/scripts/seed.py`, `dashboard/src/`, `android/app/`, the specs under `docs/specs/`
**Branch:** `campaigns`, from `main`

---

## 1. Goal

Finish the last CRUD piece, campaigns, and make the whole wellbeing workflow run end to end without Twilio. The next project is fuzz testing the API with Schemathesis. That needs a complete API, and the demo needs a workflow people can watch.

The workflow this branch makes work, on a local stack and on staging:

1. A medic registers a senior; DAS accepts them. Accepting queues the welcome call.
2. The senior's Android app shows the welcome call as a mock card. „Da” records consent and the senior becomes `active` with a green code.
3. DAS starts a campaign on the dashboard. It queues one wellbeing call per active senior.
4. The senior's app shows the campaign call as a mock card with the three questions. The answers go through the real rules: a code, and on a red an incident.
5. DAS sees the codes in the seniors list and the red on the incident board, takes it and resolves it (already built).
6. DAS ends the campaign. Calls nobody answered are canceled.

The mock replaces only the phone line. **The server step that ends a call is built for real** (§5), so the Twilio call reuses it when it arrives, reaching it through `voice/router.py` (§7). That's why the mock feeds the rules instead of writing a canned result.

Success means:

- Every endpoint in §4 exists, behaves as written, and has tests.
- The dashboard has a „Campanii” page and code chips. The Android app has the mock card and code chips.
- The workflow above runs by hand on a local stack, as the manual check in §9 describes, with a new senior on the Firebase test number `+40700000006`.
- `04`, `05`, `03`, `06` and auth-layer match the code (§8).
- No migration. `uv run pytest`, `ruff`, `lint-imports`, `alembic check`, the dashboard's checks and the Android build and unit tests all pass.

## 2. Non-goals and anti-goals

**Non-goals:**

- A scheduler or dialer, and real Twilio campaign calls (Q1). Pipeline work that waits on spike S8 and on the model provider (README open question 4).
- Push notifications: no caregiver alert on yellow, no refresh push (Q13). Apps keep re-reading on their timers.
- A call-history or transcript screen in either client (Q18).
- The DAS incident screen in Android, UC-11 (Q19). Take and resolve stay on the dashboard.
- The identity question, `wrong_number`, `not_available` and retries on the welcome call (Q15).
- Answering a mock call from anywhere but the senior's own app (Q16). A landline senior has no app, so their calls wait until the campaign ends.
- Device intake (`/me/events`, `/me/check-ins`, `/me/room-readings`) and `POST /seniors/{id}/welcome-call`.
- The telemetry gauges of `07 §4.7` (Twilio status, active calls, AI latency). There is nothing to measure.
- Declaring every refusal in OpenAPI for Schemathesis (Q6). The Schemathesis design does that, with a first run's findings.

**Anti-goals.** These would make the change a failure even if everything technically works:

- **A mock result in production.** A pilot must never get a code, an incident or a consent from a fake call (Q10).
- **A consent that claims a phone call happened.** The mock records consent with its own method (§4.4).
- **Rules forked for the mock.** The mock goes through the same ending step and the same `app/status/engine.py` functions the real call will use.

## 3. Decisions

From the grilling rounds.

| # | Decision |
|---|---|
| Q1 | `POST /campaigns` queues calls exactly as `04 §2` says. Nothing dials them; the senior's app answers them as a mock until the Twilio solution exists |
| Q2 | Campaign endpoints: `POST /campaigns`, `GET /campaigns`, plus `POST /campaigns/{id}/end` (Q9). No `GET /campaigns/{id}`, no `PATCH`, no `DELETE`: a campaign is history |
| Q3 | While a campaign of the same kind and level has an active warning, `POST` answers that campaign and creates nothing. A different kind or level starts a new one |
| Q4 | The warning lasts 24 hours from the start (`06 §3`, the same in demo mode). The body is kind and level only. The seed follows the same rule |
| Q5 | `/profile` gains `warning_active` |
| Q6 | Schemathesis is the next design, not part of this one |
| Q7 | One branch with backend, specs, dashboard and Android: the full workflow |
| Q8 | The mock is a card in the senior's Android app: the three questions as buttons, answers through the real rules. „Nu acum” counts as unanswered |
| Q9 | `POST /campaigns/{id}/end` ends the warning now and moves the campaign's queued calls to a new state, `canceled`, which no rule counts |
| Q10 | Mock endpoints refuse in production, and the app shows the card only where the server allows it |
| Q11 | The welcome call goes through the same mock, so a senior can become `active` without the seed |
| Q12 | The dashboard gets a „Campanii” page: start form, campaign list with progress, „Încheie” |
| Q13 | No notifier in this branch |
| Q14 | „Nu acum” on a campaign call queues the redial of `03 §9`, due 20 minutes later, or 20 seconds in demo mode. A second „Nu acum” ends at yellow, „no answer twice” |
| Q15 | The welcome mock is only „Da” / „Nu” |
| Q16 | Only the senior answers, in their own app |
| Q17 | `GET /seniors` and `GET /seniors/{id}` gain `code`, `reason` and `since`. Both clients show a code chip |
| Q18 | No call-history screen in the clients |
| Q19 | No DAS incident screen in Android |

## 4. The endpoints

All paths are under `/api`. Refusals use `refuse()`: `{"detail": {"reason": …}}` (`04 §0`). Request bodies end in `Form`, responses in `View`, `Summary` or `Detail` (`backend/AGENTS.md`).

### 4.1 Campaigns (new package `app/campaigns/`)

| Request | Who | Body | Effect | Answers | Refused |
|---|---|---|---|---|---|
| `POST /campaigns` | DAS | `kind` (`heat`, `cold`), `level` (`yellow`, `red`) | See below | One `CampaignSummary`: 201 when it starts a campaign, 200 when it answers the running one | Never, for DAS. A bad body is FastAPI's 422 |
| `GET /campaigns` | DAS | n/a | n/a | A list of `CampaignSummary`, newest first (`started_at` desc, then `id`). No pagination | n/a |
| `POST /campaigns/{id}/end` | DAS | none | Sets `warning_until` to the earlier of itself and now, so a lapsed warning keeps its end. Moves the campaign's `queued` calls, redials included, to `canceled` with `ended_at` now. One transaction | The `CampaignSummary`. A repeat answers the same, unchanged | No such campaign: 404 `not_found` |

**A lapsed warning ends its campaign too.** A campaign's calls live only as long as its warning. When `warning_until` passes with no „Încheie”, the campaign's queued calls are canceled exactly as `end` would cancel them. There is no scheduler, so this happens lazily: one statement, `cancel_lapsed()`, moves every `queued` call whose campaign's `warning_until ≤ now` to `canceled`. It runs first in `POST /campaigns`, `GET /campaigns`, `GET /profile/mock-call` and `POST /calls/{id}/mock-answer`. A lapsed campaign's senior is then free for the next campaign, and its card disappears.

**Starting a campaign**, in one transaction, under one advisory lock (`pg_advisory_xact_lock`, a fixed key, as in the CRUD design §5.3) so two presses at once can't both create:

1. If a campaign of the same kind and level has `warning_until > now`, answer it (200). Nothing changes.
2. Otherwise insert the campaign: `started_by` the caller, `warning_until` = `started_at` + 24 hours.
3. Queue one call per senior in `active` that has no unresolved incident and no live call: `trigger` `campaign`, `campaign_id`, `attempt` 1, `starting_severity` green, `due_at` now. Insert with `ON CONFLICT DO NOTHING` on `uq_calls_live_senior`, so a call queued for that senior in the meantime wins and the campaign skips them.

**`CampaignSummary`:** `id`, `kind`, `level`, `started_by_name`, `started_at`, `warning_until`, `active` (`warning_until > now`), and `progress`. `progress` counts each senior the campaign queued once, by that senior's **latest attempt in the campaign**:

| Count | Latest attempt |
|---|---|
| `total` | Any |
| `waiting` | `queued` |
| `green`, `yellow`, `red` | Ended, by `final_severity` |
| `canceled` | `canceled` |

A first attempt that went unanswered with its redial queued counts as `waiting`.

### 4.2 Mock calls (`app/calls/`)

| Request | Who | Answers | Refused |
|---|---|---|---|
| `GET /profile/mock-call` | A number with a `senior` grant | The caller's senior's oldest `queued` call with `due_at ≤ now`: a `campaign` call while the senior is `active`, or a `welcome` call while they are `accepted`. As `MockCallView`. 204 when there is none | `app_env` is `production`: 404 `not_found`. A caller with no `senior` grant: 403 `not_allowed` |
| `POST /calls/{id}/mock-answer` | The senior whose call it is | 204. The call ended through §5 | Production: 404 `not_found`. Not this senior's call, or no such call: 404 `not_found`. The call already ended `completed` or `unanswered`: 409 `already_done`. Any other state, `canceled` included, or a senior no longer in the state the read requires: 409 `wrong_state`, and nothing changes. A body that doesn't fit the trigger: 422 |

**`MockCallView`:** `call_id`, `trigger`, `campaign_kind` and `campaign_level` (campaign calls), and `consent_text` and `text_version` (welcome calls). The app shows exactly what the server sends, so the recorded `text_version` matches what the senior read.

**The card's consent text is its own version, `v1-app`.** The phone text (`v1`, in `seed.py` today) tells the senior to press 1 or 0, which makes no sense on a card. `v1-app` keeps `v1`'s first three sentences word for word and ends with „Sunteți de acord?”. Both texts and their versions move into the app; the seed imports `v1` from there.

**`MockAnswerForm`**, one shape per trigger:

| Trigger | Body |
|---|---|
| `campaign` | `{"feeling": "ok" \| "unwell", "day": "luni" … "duminică" \| "unknown", "shelter": "yes" \| "no"}`, or `{"declined": true}` for „Nu acum” |
| `welcome` | `{"consent": true \| false}` |

A number holds at most one senior grant (`uq_grants_one_senior_per_user`, `05 §3`, SE10), so "the caller's senior" is well defined.

### 4.3 Changes to existing endpoints

| Request | Change |
|---|---|
| `GET /profile` | Adds `warning_active: bool`, true while any campaign has `warning_until > now`, for every caller |
| `GET /seniors`, `GET /enrollments`, the answers of submit, accept and consent-withdrawn (`SeniorSummary`) | Add `code` (`green`, `yellow`, `red` or null), `reason` (string or null) and `since` (time or null), from `senior_status`. Null until the senior's first result, and null for any senior who is not `active`: a withdrawn senior's old green must not read as "being watched" (`05 §2`: one current code per active senior) |
| `GET /seniors/{id}` (`SeniorView`) | The same three fields, on `SeniorView`, not on `SeniorDetail`: `SeniorDetail` is also inside `IncidentDetail`, and the incident page doesn't change |
| `POST /seniors/{id}/accept` | Also queues the welcome call, in the same transaction: `trigger` `welcome`, `attempt` 1, `starting_severity` green, `due_at` now. `04 §2` already says so. A senior whose number is a landline gets the call too; it waits, as for a campaign |
| `POST /seniors/{id}/consent-withdrawn` | Also cancels the senior's `queued` calls, in the same transaction, so a withdrawn senior „gets no more calls” (UC-04) and their card goes |

All of these only add fields or rows. Old apps ignore new fields (ADR-001 §2.3).

### 4.4 New enum members

Stored as `VARCHAR(32)` with no `CHECK` (`StoredEnum`), so no migration. `alembic check` must stay clean.

- `CallState.canceled`: ended, reached only from `queued`. `TRANSITIONS[queued]` gains it; `ENDED` picks it up on its own. Not answered, and §5 never runs on it.
- `ConsentMethod.app`: a consent given or refused through the mock card.

## 5. Ending a call

Two layers in `app/calls/`, in one transaction:

- **The mock's own part** locks the call row and checks it is still `queued`, and that the senior is still in the state the read requires (§4.2). It then walks the call through the same states a real call passes, with `advance()` and no change to `TRANSITIONS` beyond `canceled`: `queued → ringing → in_progress` for an answer, `queued → ringing → unanswered` for „Nu acum”. `started_at` is set when it reaches `in_progress`.
- **The shared ending step** takes a call that is already `in_progress` (answered) or already `unanswered`, the answers, and the session. It does everything below that isn't the walk. This is the part a Twilio call reuses. Since `voice` can't import `calls` (a cycle), the relay will reach it through `voice/router.py`, which may import anything. Wiring that up is the Twilio work, not this branch.

**A campaign call, answered** (all three answers given):

1. The call moves `in_progress` → `completed`, with `ended_at` now.
2. It writes the transcript as `call_turns`: the greeting naming the warning, each question, and each button label as the senior's reply, then the goodbye. The text is Romanian and follows `04 §4`'s greeting and the seed's wording.
3. It writes three `answers` (`clear` true, `quote` the button label).
4. It runs `CallAnswers.severity(today_in_bucharest())`, `certainty()` (always high, since every answer is clear) and `final_severity(starting=green, answered=True, …)`. It writes `final_severity`, `final_certainty`, a Romanian `reason` naming what was worrying (like the seed's „Se simte rău și nu are căldură”), a short `summary`, and one `status_reports` row with source `rules`.
5. It sets the code with `next_code()`, upserting `senior_status` (`source_call_id` the call, `since` now).
6. If `opens_incident()` holds, it opens an incident: status `open`, `opened_by_call_id` the call, the call's reason.

A mock red ends the call as `completed`, not `handed_over`: there is no line to hand over and no on-duty phone rings. The incident opens all the same.

**A campaign call, declined** („Nu acum”):

1. The call is `unanswered` (the walk above), with `ended_at` now, and gets a `status_reports` row with source `unanswered`.
2. If it was attempt 1, a redial is queued: a new call with `previous_call_id`, `attempt` 2, the same `campaign_id` and starting severity, and `due_at` now + the redial delay (20 minutes, 20 seconds when `demo_mode` is on). No code changes, since a campaign's green waits for the redial (`03 §6`).
3. If it was attempt 2, the result is `final_severity(starting=green, answered=False)`, which is yellow, with reason „Nu a răspuns de două ori”. The code is set as in step 5 above.

**A welcome call:**

| Answer | Effect |
|---|---|
| `consent: true` | Call `completed`, `welcome_outcome` `confirmed`. A consent row: `given`, method `app`, `text_version` `v1-app`, `call_id` the call. Senior `accepted` → `active`. A first `senior_status`: green, reason „Consimțământ dat”, `since` now (`03 §8`: the code starts when consent is given) |
| `consent: false` | Call `completed`, `welcome_outcome` `confirmed`. A consent row: `refused`, method `app`, `text_version` `v1-app`. Senior `accepted` → `refused`. No code |

The transcript holds the card's consent text and „Da” or „Nu”. The senior's move uses the same guarded update as `seniors.service.move()` (only where still `accepted`). That function lives in `seniors`, which `calls` may import.

## 6. Clients

All new UI text is Romanian.

### 6.1 Dashboard

- **„Campanii” page**, a new sidebar entry at `/campaigns` (Q12):
  - Start form: kind (Caniculă / Ger) and level (galben / roșu), and a „Lansează” button. It shows the answer, whether the campaign is new or the running one.
  - The list from `GET /campaigns`: kind, level, who started it and when, when the warning ends, and the progress counts as a bar or row of numbers.
  - „Încheie” on each active campaign.
  - The page re-reads on the existing poll (`utils/poll.svelte.ts`).
- **Code chips** in the seniors list (`features/seniors/Seniors.svelte`) and the senior details, with the reason. The comment saying the API sends no codes goes. Colors follow `utils/labels.ts`.
- A label for the `canceled` call state, wherever call states are labeled.

### 6.2 Android

- **The mock card**, on the senior's own home (`OwnRoute`, `SeniorScreen` with `id` null). It reads `GET /profile/mock-call` on the screen's existing re-read (`RereadWhileShown`). On 204 or 404 there's no card.
  - **Campaign:** „DAS Timișoara vă sună” and the warning. Then the three questions, each with big buttons: „Cum vă simțiți?” (Bine / Rău); „Ce zi este azi?” (the seven days, and „Nu știu”); „Aveți căldură în casă?” for cold or „Aveți un loc răcoros?” for heat (Da / Nu). Then one post. „Nu acum” posts `declined`.
  - **Welcome:** the consent text from the server, and „Da” / „Nu”.
  - After the post, the card goes and the page re-reads. A 409 just re-reads.
- **`warning_active`**: the senior's home shows one line while it is true, for example „Avertizare meteo în vigoare”.
- **Code chips** on the medic's and caregiver's senior cards (`SeniorsScreen`) and on the senior page, with the reason. Colors from `ui/theme/Palette.kt` (verde, galben, roșu).
- `SeniorRow`, `SeniorPage` and `Me` gain the new fields as optional, so the app still parses an older server. A label for `withdrawn` isn't in scope here (CRUD design §9).
- JVM unit tests next to the existing ones, for the answer body built from the buttons and for the chip's mapping from code.

## 7. How it fits the code

**Packages and the import graph.** Today `voice → seniors → auth`, `incidents → voice`, and `calls → incidents, voice, seniors`. `lint-imports` forbids cycles between packages; routers sit above everything.

- `app/campaigns/` (new): `router.py`, `service.py`, `schemas.py`, an empty `__init__.py`; the `Campaign` model stays in `voice/models.py`. It imports `voice`, `seniors` and `incidents` (to skip seniors with an unresolved incident). Mounted in `main.py`.
- The ending step (§5) and the mock endpoints go in `app/calls/`, which already imports `incidents`, `voice` and `seniors`.
- `seniors` can't import `voice` (a cycle). So the welcome call that accept queues, and the canceling that withdrawal does, are functions in `calls/service.py`, which the seniors router calls inside the same session before the commit. The seniors service then stops committing on its own for those two, or commits once after both. Builder's choice, as long as each is one transaction.
- `warning_active` is a query in `campaigns/service.py` that `auth/router.py` calls. `auth/service.py` can't import `voice`.
- The code fields on `SeniorSummary` and `SeniorView` come from an outer join to `senior_status` in `seniors/service.py`, limited to `active` seniors. Every query that builds a `SeniorSummary` gets it.

**`uv run lint-imports` passes without changing a contract.** If one has to change, stop and say why.

**Production gate.** `get_settings().app_env is AppEnv.production` refuses both mock endpoints. Nothing else about them differs between environments, so Schemathesis sees the same API locally.

## 8. Spec documents to update

| File | Change |
|---|---|
| `docs/specs/echocare/04-interfaces.md` | §0: the repeat rule for `POST /campaigns` (the running campaign answers). §1: `GET /campaigns`, `GET /profile/mock-call`, `warning_active` on `/profile`, the code fields on the seniors rows. §2: `POST /campaigns` as in §4.1, `POST /campaigns/{id}/end`, `POST /calls/{id}/mock-answer`; consent-withdrawn cancels queued calls; a lapsed warning cancels its campaign's queued calls. Mark the mock rows as demo only, refused in production |
| `docs/specs/echocare/05-data-model.md` | `call.state` gains `canceled`. `consent.method` gains `app`. The campaign's `warning_until` is 24 hours after the start |
| `docs/specs/echocare/03-status-model.md` | §9: `queued → canceled` when a campaign ends, counted by no rule |
| `docs/specs/echocare/06-operations.md` | §3's demo controls: the mock card, standing in for the phone line, refused in production |
| `docs/specs/echocare/02-use-cases.md` | UC-04 and UC-05: a note that until Twilio, the mock card answers the call |
| `docs/specs/auth-layer.md` | `warning_active` has arrived (§3.3 and the later-fields lists) |
| `docs/specs/echocare/README.md` | Nothing, unless an open question changes |
| `backend/README.md` | The test-number table gains `+40700000006` / `666666`, a second senior, for the welcome card |

## 9. Tests and rollout

**Backend tests.** Follow the existing files: a new `tests/campaigns/`, and `tests/calls/` for the ending step and the mock endpoints. As `06 §5` asks, call every new endpoint as each role, as a number with no grant, and signed out. Cover at least:

- Starting: who gets queued and who is skipped (an unresolved incident, a live call, not `active`). The same kind and level answers the running one; another level starts a new one.
- Ending a campaign: queued calls and redials are canceled, the codes are untouched, a repeat changes nothing, and a new campaign can start afterwards. Ending a lapsed campaign keeps its `warning_until`.
- A lapsed warning: its queued calls are canceled by the next of the four endpoints in §4.1, and its senior is queued by the next campaign.
- Withdrawal cancels the senior's queued calls, and the mock read serves nothing to a senior who isn't in the right state.
- `progress` counts by the latest attempt.
- The ending step: green, yellow and red from button answers, with the day checked against Bucharest's today. A red opens an incident, and a red with an incident still open is never lowered (`next_code`). A first „Nu acum” queues a redial due later. A second ends at yellow.
- The welcome call: Da → `active` with a green code; Nu → `refused`; a senior no longer `accepted` → 409.
- Both mock endpoints answer 404 with `app_env` production.
- `warning_active`, and the code fields on the seniors rows, null for a senior who isn't `active`.

The ending step's rules are already covered by `tests/status/`; these tests check the database writes around them.

**Dashboard and Android.** Their existing checks, plus the unit tests in §6.2.

**Manual check.** On a local stack (`docker compose up --watch`, then `uv run python scripts/seed.py --reset`). `+40700000006` with code `666666` is a Firebase test number, added in the console by the team. Report each step as checked or not checked:

| # | Who, where | Does | Sees |
|---|---|---|---|
| 1 | Medic `+40700000002` / `222222`, Android | „Pacient nou”: a senior on `+40700000006`, with a street, a number and one caregiver. Submits | The senior in `submitted` |
| 2 | DAS `+40700000001` / `111111`, dashboard | „Cereri înrolare”: accepts the senior | The senior in `accepted`, no code chip |
| 3 | Senior `+40700000006` / `666666`, Android | Signs in. The welcome card shows the `v1-app` text. „Da” | Within one re-read the card goes. The senior is `active` with a green chip, here and on the dashboard |
| 4 | DAS, dashboard | „Campanii”: ends the seed's running campaign with „Încheie”, then starts Ger / galben | A new campaign. Its `total` counts every active senior without an unresolved incident, Maria and the new senior among them |
| 5 | Senior, Android | The campaign card („DAS Timișoara vă sună”). „Nu acum” | The card goes. Within the redial delay (20 seconds in demo mode) it comes back |
| 6 | Senior, Android | Answers Rău, a wrong day, Nu (no heating) | Red chip. On the dashboard, an open incident on the board and `red` 1 in the campaign's progress |
| 7 | DAS, dashboard | Takes and resolves the incident | The incident resolved. The senior's chip stays red until their next result (`03 §8`) |
| 8 | DAS, dashboard | „Încheie” on the campaign | `waiting` goes to 0 and `canceled` counts the seniors nobody answered for. The senior's home loses the warning line |
| 9 | Senior `+40700000005` / `555555`, Android | Optional, between steps 4 and 8, if that number is in the Firebase console: the seed's Maria answers Bine, today's day, Da | A green chip for Maria, and `green` 1 in the progress |

Step 6 shows the redial from step 5 ending red, which also shows a declined first attempt doesn't block a later answer.

**Old clients.** Every API change adds a field, a row or an endpoint. Today's Android build ignores the new fields and never asks for a mock call. A `canceled` state reaches today's clients as an unknown word, which both show raw.

**The seed.** Its cold/yellow campaign follows Q4: `warning_until` is 24 hours after its start, so after `--reset` it is still running. Pressing Ger / galben then answers the seed's campaign, which is correct (Q3). The manual check ends it first, or starts Ger / roșu. The seed queues no calls.

**Rollout.** One PR from `campaigns` into `main`. No migration and no new setting. Merging redeploys staging's `api` and `dashboard`. Since the branch touches all three folders, all three CI workflows run, and Railway's Wait for CI holds the API deploy if the Android build is red (`AGENTS.md`). Staging has no seed and gets no backfill: a senior accepted there before this change has no welcome call, and stays `accepted` until `POST /seniors/{id}/welcome-call` exists. The workflow on staging starts from a fresh registration.

## 10. Calls made while writing this

Small choices nobody was asked about. Check them while reading:

1. `POST /campaigns` answers 201 for a new campaign and 200 for the running one.
2. Starting a campaign takes one advisory lock, so two presses at once create one campaign.
3. `progress` counts each senior once, by their latest attempt in the campaign.
4. Ending a campaign answers the campaign and is repeat-safe; it doesn't refuse an already-ended one.
5. The mock read is `GET /profile/mock-call`, answering 204 when there's nothing. The answer is `POST /calls/{id}/mock-answer`.
6. A senior can see only calls due now: a redial's card appears when its due time comes.
7. The day question has „Nu știu”, which counts as a wrong day, as for a real call.
8. A mock red ends `completed`, not `handed_over`, and rings nobody.
9. The welcome call's consent text and version come from the server, and move out of `seed.py`. The card gets its own version, `v1-app`, without the key-press instructions.
10. Welcome „Da” gives a first green code with reason „Consimțământ dat”.
11. The mock gate is `app_env` production, not `demo_mode`. `demo_mode` keeps meaning only shorter timers.
12. The senior's home shows a one-line warning while `warning_active` is true. No other screen uses the flag.
13. Accept queues the welcome call for a landline senior too. It waits like a campaign call.
14. A lapsed warning cancels its campaign's queued calls, lazily, on the next campaign or mock request. No scheduler.
15. Withdrawing consent cancels the senior's queued calls in the same transaction.
16. The code fields are null for any senior who isn't `active`.
17. The mock walks a call through `ringing` like a real one, so `TRANSITIONS` only gains `canceled`. The shared ending step starts from an answered or unanswered call, so the Twilio relay can use it.
18. No staging backfill for seniors accepted before this change.
