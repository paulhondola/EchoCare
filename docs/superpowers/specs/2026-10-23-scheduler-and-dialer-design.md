# Scheduler and dialer — design

Date: 2026-10-23. Status: drafted from a grilling session on [issue #47](https://github.com/paulhondola/EchoCare/issues/47), reviewed by a builder check; approved 2026-10-24.

## Intent

A queued call should dial itself when it comes due. Today nothing does: campaigns, redials and welcome calls only ever become mock cards, because the scheduler loop of 06 §2 was never built. Every real call waits on this. The change builds that loop inside FastAPI, with its dialer, a sweep for calls Twilio never reported on, and the watch's silence step, and proves it on the local stack.

## Goals

- A loop in FastAPI's lifespan ticks every few seconds and works only while it holds a Postgres advisory lock (G9), so one copy runs during a deploy.
- Queued calls that are due are dialed through Twilio, up to a limit of calls live at once.
- A real call that is not answered, is busy or fails runs the existing redial-and-yellow rule (`calls/ending.py` `conclude`), as the mock card's „Nu acum” does.
- A call Twilio never reported on is settled after a limit, from Twilio's own record.
- Lapsed campaign warnings cancel their queued calls on the tick; the lazy path stays as a fallback.
- `POST /me/check-ins` stores the watch's latest check-in, and the tick marks a silent watch `offline` (UC-13). The watch app's developer builds against this endpoint.

## Done when

On the local stack with Twilio credentials and a tunnel, accepting a senior rings their phone without anyone running `place_call.py`, and a call left `in_progress` with no status callback is settled after the limit.

## Non-goals

- **The real welcome call.** The identity and consent conversation of UC-04 comes later. Here a welcome call speaks a fixed sentence and hangs up (§5). A senior who got it stays `accepted`: they never give consent, and that is accepted for now.
- **Welcome-call retries and `unreachable`.** An unanswered stand-in welcome call just ends `unanswered`.
- **Codes from answered real calls.** The relay ends an answered wellbeing call `completed` without answers, so it sets no code. A call that ends `dropped`, in the sweep too, sets no code either. Both belong to the agent's work.
- **Showing watch state.** No read (`GET /seniors/{id}`, `/profile`) gains the watch's state. Whoever builds the device warning in the apps adds it.
- **Push.** 06 §2's "refresh" after a watch goes offline is not sent. No push sender exists yet.
- **Staging and production dialing.** Developed and proven locally. An empty `DIAL_ALLOWLIST` dials nobody, production included (your call), so merging to `main` or `release` places no call until someone sets the list, or `*`, on that environment. Until then staging keeps its mock card, and production queues calls as today.
- **The home node's steps** (P20, proposed) and the redial rule's content, which already exists.
- **Priorities.** Due calls are dialed in id order (§3).

## Anti-goals

- A call dialed twice. Every path below exists to make that impossible, a crash between two steps included.
- A ringing phone whose call is marked `canceled` because its campaign lapsed a moment after the dial.
- A mock card and a real line both answering the same call.
- A settled-late call ending differently from one Twilio reported on time.

## Constraints

- Old clients and old copies talk to new servers (ADR-001 §2.3): the migration only adds, new fields optional.
- Only a table's owner writes it (ADR-005). `calls` belongs to `voice`, `watch_states` to `seniors`, `campaigns` to `campaigns`. The scheduler calls their functions.
- The scheduler is a new package `app/scheduler/` and must be placed in the layers contract in `pyproject.toml`, above `calls | agent | system`, since it uses all of them. `uv run lint-imports` must pass.
- `check_environment()` already refuses a laptop scheduler on a cloud database. Keep it and its tests.
- Tests run against `echocare_test` with the loop off; they call one tick directly.
- User-facing text is Romanian.

## Design

### 1. The `dialed_at` marker

A nullable `dialed_at` timestamp on `calls`, set when the dialer takes a call and committed **before** Twilio is asked. That one column covers everything that "already dialed" has to mean:

- The dialer picks only queued calls with no `dialed_at`.
- `cancel_queued`, used for lapsed and ended campaigns and withdrawals, cancels only calls with no `dialed_at`. A dialed call ends through Twilio.
- `GET /profile/mock-call` and `POST /calls/{id}/mock-answer` ignore or refuse a dialed call (`wrong_state`), so the card and the line never race.
- The sweep measures "stuck" from `dialed_at`.

Twilio's `initiated` and `queued` statuses still change nothing (03 §9): a dialed call stays `queued` until `ringing`. Old copies that don't know the column dial nothing, since they have no scheduler.

### 2. The loop

- Started from FastAPI's lifespan when `scheduler_enabled` is on; stopped on shutdown. The test setup turns it off.
- Every 5 seconds (a constant). Each tick takes `pg_try_advisory_lock` on one connection and holds it for the whole tick, then releases it. It is session-level, not transaction-level, because the dialer commits mid-tick. If another copy holds the lock, the tick does nothing.
- A step that raises is logged with its traceback and the next step still runs. A tick that fails does not stop the loop.
- Steps in order: cancel lapsed warnings → dial → sweep → watch silence.

### 3. The dialer

- **Lines.** `MAX_LIVE_CALLS` setting, default 3 (06 §3, "calls in progress at once"). It is a cap in our code, not a number of Twilio numbers: one number carries several calls. Lines in use = calls with `dialed_at` set in a live state. Free lines = the cap minus those.
- **Which calls.** Queued, `dialed_at` null, `due_at` ≤ now, in id order (uuidv7, so creation order), up to the free lines. The same trigger-and-enrollment filter as the mock card applies: a campaign call needs an `active` senior, a welcome call an `accepted` one.
- **Allowlist** (your call: added so a seeded or mistyped number is never rung). `DIAL_ALLOWLIST`, a comma-separated list of numbers, normalized to E.164 as everywhere else. Only a call whose senior's number is on it is dialed; any other stays queued for the mock card, logged once at info. Empty (the default) dials nobody; `*` dials everyone. `scripts/place_call.py` honors it too. The seeded seniors' numbers are replaced by hand with the team's own before testing; the seed itself is not changed.
- **No Twilio.** If `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` or `TWILIO_FROM_NUMBER` is empty, the dialer does nothing. The queue and the mock card behave exactly as today.
- **Per call.** Stamp `dialed_at`, commit, then `voice.twilio.dial`. The answer URL is `/voice/welcome` for a welcome call and `/voice/answer` for every other trigger.
  - Success: store the `sid` as `twilio_call_id` (a callback may have stored it first; it is the same id).
  - Twilio refuses (a 4xx status): the call becomes `failed` and goes through the settle step (§4), so the redial rule applies (06 §1).
  - Timeout, no connection, or a 5xx (*my call*): Twilio may have placed it. It stays `queued` with its stamp and no `sid`; a callback or the sweep settles it.
- `scripts/place_call.py` keeps dialing directly, sets `dialed_at` on its call so the scheduler never dials it too, and on a timeout prints "outcome unknown" instead of marking the call failed.

### 4. Settling a call by Twilio's word

One function, used by `POST /voice/status`, by voicemail detection (`POST /voice/amd`, which today moves the call through `voice.service.machine_answered` and would conclude nothing; the router calls the settle function, then hangs up as now) and by the sweep. Voicemail runs the redial rule, as 06 §1 says. It lives in `calls` (it needs `calls.ending.conclude`); the voice router may import it, as routers sit above every layer.

- It applies Twilio's status as `move_call` does today (skip ahead, never back, an ended call stays ended).
- If **this** move ended the call `unanswered` or `failed`, it runs `conclude(session, call, None)`: a first attempt queues the redial and changes no code; a second ends at yellow, „Nu a răspuns de două ori”. A repeated callback that moves nothing concludes nothing.
- `welcome` and `test` calls are moved but never concluded: no rule counts a test call (05 §1), and welcome retries are a non-goal.
- `dropped` and `completed` are moved only (non-goal: codes from answered calls).

### 5. The stand-in welcome call

`POST /voice/welcome` (signed, as every callback). It marks the call `completed` (a skip ahead from `ringing` is allowed), then answers TwiML that says one Romanian sentence in the configured voice and hangs up: „Bună ziua, {form of address}. Acesta este un apel de test EchoCare. La revedere.” Marking it `completed` first matters: Twilio's later `completed` callback would otherwise turn it into `dropped`. No `welcome_outcome`, no consent, no code. The real UC-04 steps later replace this handler at the same address.

### 6. The sweep

A call in a live state whose `dialed_at` is older than ring time (30 s) + call length limit (3 min) + 1 minute:

- **With a `sid`:** read `GET …/Calls/{sid}.json`. If Twilio still has it live, hang up, then read it again. Settle it through §4 with Twilio's final status.
- **Without a `sid`:** it becomes `failed` through §4, but only if its state is still the one the sweep read. A callback that lands at the same moment wins.
- Every call the sweep settles is logged at warning level, with its id, its state before, its state after, and Twilio's status.
- A Twilio error on one call is logged, and the sweep goes on to the next; the call is tried again next tick.

### 7. Lapsed warnings on the tick

The tick runs `campaigns.service.cancel_lapsed`. The lazy calls in the campaign and mock endpoints stay, as a fallback when the scheduler is off.

### 8. Check-ins and the silence step

**`POST /me/check-ins`**, the senior only (04 §3). Body: `measured_at`, `battery` (0–100, optional), `worn` (bool, optional), `last_pulse` (optional). It upserts the senior's one `watch_states` row: `worn` false sets `not_worn`, anything else `ok`, which also brings an `offline` watch back (UC-13 step 3). A `measured_at` in the future is stored as the time it arrived (*my call*: a wrong watch clock must not keep a watch `ok` past its silence). A check-in measured before the stored one is acknowledged and changes nothing, since the phone resends held-back check-ins on reconnection. It is stored whatever the senior's enrollment state, and starts no call. Answers 204. Only the latest is kept (05 §5).

**Silence step.** A watch in `ok` or `not_worn` whose `last_check_in_at` (measured time) is older than the silence limit becomes `offline`: 45 minutes, or 90 seconds in demo mode (06 §3), picked from `demo_mode` as `redial_delay` does. No alert, no code change, logged.

### 9. Settings and docs

- `MAX_LIVE_CALLS` and `DIAL_ALLOWLIST` on `Settings` and in `.env.example`.
- **Twilio in Ireland (your call: data residency).** `TWILIO_API_HOST`, default `api.twilio.com`; set to `api.dublin.ie1.twilio.com` so calls are created, processed and logged in IE1. `voice/twilio.py`'s `API` constant becomes this setting, for the dial, the hang-up and the sweep's read. `TWILIO_AUTH_TOKEN` then holds the IE1 auth token, since credentials are valid only in their region. Two things are unconfirmed in Twilio's docs and are checked once with `place_call.py` before the scheduler is built: that IE1 signs callbacks with the IE1 token (a 403 on every callback says no), and that voicemail detection runs in IE1. ConversationRelay is documented as available there.
- `backend/README.md`: how to run real calls locally (Twilio variables, a tunnel such as `cloudflared` or `ngrok`, `PUBLIC_BASE_URL` set to it). Without a tunnel the phone rings, no callback arrives, and the sweep settles the call.
- Spec updates, in this change: 06 §4 (Twilio processes calls in IE1, the number is Romanian, not US); 06 §1 (the restart and deploy rows: dialed calls and the lock), §2's flowchart (lapsed warnings and the sweep, the order of §2 above); 04 §2's lapsed-warning paragraph (the scheduler now, lazy as fallback), the mock rows (dialed calls refused); 04 §3 the check-in body; 04 §4.2 the stand-in welcome row and the redial on unanswered; 05 the `dialed_at` column.

## Tests

- Two schedulers, one tick: only one dials.
- The line limit: with 3 live, nothing more is dialed; with 1 live, 2 are.
- A due and a not-yet-due call; id order among due calls.
- A dialed call is not dialed again on the next tick, with a `sid` and without (timeout).
- No Twilio variables: nothing dialed, the mock card still shows the call.
- Allowlist: a listed number is dialed; an unlisted one stays queued and keeps its card; empty dials nobody; `*` dials everyone.
- A lapsed campaign's undialed call is canceled on the tick; its dialed call is not.
- Twilio refuses: `failed`, and a first attempt's redial is queued.
- `no-answer` on a first campaign attempt queues a redial; on a second ends yellow; a repeated callback queues nothing more. Voicemail detected on a first attempt queues a redial too. A welcome or test call is not concluded.
- The stand-in welcome: answers TwiML with the sentence and a hang-up, the call is `completed`, and a later `completed` callback leaves it `completed`.
- Sweep: a call stuck `in_progress` with a `sid` (Twilio says completed); one Twilio still has live (hang-up, then settled); one stuck `ringing` without a `sid`; a call inside the limit left alone.
- Check-ins: first one creates the row; `worn` false sets `not_worn`; an older one changes nothing; a non-senior is refused. Silence: past the limit goes `offline`, inside stays; a check-in after brings it back to `ok`.
- Twilio's HTTP calls are replaced by a stand-in in tests; nothing reaches Twilio.

## Left to the builder

- Module layout inside `app/scheduler/` and the names of new functions.
- How the stand-in for Twilio is wired in tests.
- How the hang-up in §6 picks Twilio's `Status` value (`canceled` for a call still queued or ringing at Twilio, `completed` for one in progress).
- The migration's name.
