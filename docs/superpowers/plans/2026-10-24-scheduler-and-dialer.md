# Scheduler and Dialer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Queued calls dial themselves through Twilio when due, unanswered real calls run the redial rule, stuck calls are settled, and silent watches go offline (issue #47).

**Architecture:** A new `app/scheduler/` package runs a 5-second loop from FastAPI's lifespan; each tick holds a session-level Postgres advisory lock and runs four steps through the owning packages' functions (ADR-005). A nullable `calls.dialed_at` marks a call taken by the dialer. One settle function in `calls/ending.py` applies Twilio's word to a call for the status callback, voicemail detection and the sweep.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async + asyncpg, Alembic, httpx, pytest (asyncio auto), import-linter.

**Spec:** [docs/superpowers/specs/2026-10-23-scheduler-and-dialer-design.md](../specs/2026-10-23-scheduler-and-dialer-design.md)

## Global Constraints

- All commands run from `backend/`. Tests: `uv run pytest`; lint: `uv run ruff check .`, `uv run ruff format --check .`, `uv run lint-imports`. All four pass at every commit (lefthook runs them; never `--no-verify`).
- Migrations only add; the new column is nullable. Migrations on `main` are frozen.
- Only a table's owner writes it (ADR-005): `calls` → `app/voice/service.py`, `watch_states` → `app/seniors/service.py`, `campaigns` → `app/campaigns/`. `test_only_the_owner_writes_a_table` enforces it.
- Import a name from the module that defines it; no imports inside functions; tests patch a name in the module that uses it.
- New settings go on `Settings` and in `backend/.env.example`.
- User-facing text is Romanian; code, comments and docs English, citing the spec by ID (`06 §3`, `UC-13`).
- Tests never reach Twilio: patch the `app.voice.twilio` functions where they are used.
- Values: tick 5 s; `MAX_LIVE_CALLS` default 3; ring 30 s (`RING_SECONDS`); call limit 3 min; sweep margin 1 min; watch silence 45 min, 90 s in demo mode; IE1 host `api.dublin.ie1.twilio.com`; default host `api.twilio.com`.
- `DIAL_ALLOWLIST`: comma-separated numbers; empty dials nobody, in every environment; `*` dials everyone.
- Stand-in welcome sentence: `Bună ziua, {form_of_address}. Acesta este un apel de test EchoCare. La revedere.`

## Review Focus

- **Allowlist written as people type numbers** (`0722 123 456`, spaces, a trailing comma): matched after E.164 normalization; an invalid entry stops the API at startup rather than silently dialing nobody. Test in Task 1.
- **A campaign ended while a dial is in flight:** the call was stamped and committed first, so the cancel leaves it and Twilio's callbacks end it. Test in Task 2.
- **A naive or future `measured_at` from a watch with a wrong clock:** naive is FastAPI's 422; future is stored as arrival time so the watch can still go silent. Test in Task 7.
- **Twilio slow or down during a tick:** a timeout leaves the call queued with its stamp and is never re-dialed; ticks never overlap because the loop sleeps after each one. Test in Task 5.
- **A tick that raises in one step:** the other steps still run and the loop survives. Test in Task 8.

---

### Task 1: Twilio host, allowlist and line settings; read and hang up a call

**Files:**
- Modify: `app/core/settings.py`, `.env.example`
- Modify: `app/voice/twilio.py`
- Test: `tests/voice/test_twilio.py`, `tests/core/test_settings.py`

**Interfaces:**
- Produces:
  - `Settings.twilio_api_host: str = "api.twilio.com"`, `Settings.max_live_calls: int = 3`, `Settings.dial_allowlist: str = ""` (validator normalizes each entry to E.164 with `app.core.phones.normalize`, drops blanks, keeps a lone `*`; an invalid entry raises `ValueError`).
  - `twilio.configured() -> bool`: all three of SID, token, from-number set.
  - `twilio.dial_allowed(phone_e164: str) -> bool`: `*` → True, empty → False, else membership.
  - `twilio.dial(to: str, call_id: uuid.UUID, answer: str = "answer") -> str`: `answer` is the callback path (`"answer"` or `"welcome"`).
  - `twilio.refused(error: httpx.HTTPError) -> bool`: True only for an `HTTPStatusError` with a 4xx status.
  - `twilio.fetch_status(sid: str) -> str`: Twilio's `status` from `GET …/Calls/{sid}.json`.
  - `twilio.hang_up(sid: str, status: str = "in-progress") -> None`: posts `Status=canceled` when `status` is `queued` or `ringing`, else `Status=completed`.
  - All requests go to `https://{twilio_api_host}/2010-04-01/Accounts/{sid}/…`.

- [ ] **Step 1: Write the failing tests**

```python
def test_allowlist_normalizes_and_drops_blanks():
    s = Settings(database_url="postgresql://x@localhost/x", dial_allowlist="0722 123 456, ,+40722000001,")
    assert s.dial_allowlist == "+40722123456,+40722000001"

def test_allowlist_refuses_an_invalid_number():
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://x@localhost/x", dial_allowlist="12")

@pytest.mark.parametrize("allowlist, phone, allowed", [
    ("", "+40722123456", False),
    ("*", "+40722123456", True),
    ("+40722123456", "+40722123456", True),
    ("+40722123456", "+40722000001", False),
])
def test_dial_allowed(monkeypatch, allowlist, phone, allowed):
    monkeypatch.setattr(get_settings(), "dial_allowlist", allowlist)
    assert dial_allowed(phone) is allowed

def test_refused_is_a_4xx_only():
    # HTTPStatusError 400 → True; 500 → False; httpx.ConnectTimeout → False

async def test_requests_go_to_the_configured_host(monkeypatch):
    # httpx.MockTransport (patch httpx.AsyncClient in app.voice.twilio) records the URL;
    # with twilio_api_host="api.dublin.ie1.twilio.com", dial() posts to
    # https://api.dublin.ie1.twilio.com/2010-04-01/Accounts/AC1/Calls.json
    # and its Url form field ends with /api/voice/welcome?call=<id> when answer="welcome"

async def test_hang_up_cancels_a_ringing_call_and_completes_a_live_one(monkeypatch):
    # hang_up(sid, "ringing") posts Status=canceled; hang_up(sid, "in-progress") Status=completed

async def test_fetch_status_reads_the_call(monkeypatch):
    # GET …/Calls/CA1.json answering {"status": "completed"} → "completed"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/voice/test_twilio.py tests/core/test_settings.py -v`
Expected: FAIL (`ImportError` for `dial_allowed`, unknown settings fields).

- [ ] **Step 3: Implement the settings and the functions above**

Replace the `API` constant with the setting; route `_post` and a new `_get` through one URL builder. Add `TWILIO_API_HOST`, `MAX_LIVE_CALLS`, `DIAL_ALLOWLIST` to `.env.example` with a one-line comment each (IE1 host and its own auth token; "empty dials nobody, * everyone").

- [ ] **Step 4: Run the tests and lint**

Run: `uv run pytest tests/voice tests/core -q && uv run ruff check . && uv run lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core/settings.py app/voice/twilio.py .env.example tests/voice/test_twilio.py tests/core/test_settings.py
git commit -m "backend: Twilio host, dial allowlist and line limit settings (#47)"
```

- [ ] **Step 6: Checkpoint (human, before Task 5): the IE1 test call**

Ask the user to set the IE1 auth token, `TWILIO_API_HOST=api.dublin.ie1.twilio.com`, the tunnel's `PUBLIC_BASE_URL` and `TWILIO_FROM_NUMBER` in `backend/.env`, then run `docker compose exec api python scripts/place_call.py <their mobile>`. Passed when the phone rings, repeats what is said, and `docker compose logs api` shows status callbacks (not `refused not_allowed`) and an `answered by` line. A 403 on every callback means IE1 signs with another token: stop and report.

---

### Task 2: `calls.dialed_at`; cancel and the mock card leave dialed calls alone

**Files:**
- Create: `alembic/versions/<rev>_calls_dialed_at.py` (revises `b3e9c1d47a52`)
- Modify: `app/voice/models.py` (`Call.dialed_at: Mapped[datetime | None]`, timezone-aware)
- Modify: `app/voice/service.py` (`cancel_queued`), `app/calls/mock.py` (`due_mock_call`, `answer_mock_call`)
- Test: `tests/campaigns/test_campaigns.py`, `tests/calls/test_mock_calls.py`

**Interfaces:**
- Produces: `Call.dialed_at`; `cancel_queued` cancels only rows with `dialed_at IS NULL`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_a_lapsed_campaign_leaves_a_dialed_call(db, ...):
    # two queued calls of one lapsed campaign; one has dialed_at set
    # after cancel_lapsed: the undialed one is canceled, the dialed one still queued

async def test_ending_a_campaign_leaves_a_dialed_call(client, db, ...):
    # POST /api/campaigns/{id}/end → dialed call still queued

async def test_the_card_skips_a_dialed_call(client, db, ...):
    # due queued campaign call with dialed_at set → GET /api/profile/mock-call is empty (as for no call)

async def test_answering_a_dialed_call_is_wrong_state(client, db, ...):
    # POST /api/calls/{id}/mock-answer → 409, code "wrong_state", call unchanged
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/campaigns tests/calls/test_mock_calls.py -q`
Expected: FAIL (`dialed_at` unknown).

- [ ] **Step 3: Write the migration (`op.add_column("calls", sa.Column("dialed_at", sa.DateTime(timezone=True), nullable=True))`, downgrade drops it), the column, and the two filters (`Call.dialed_at.is_(None)` in `cancel_queued` and `due_mock_call`; `call.dialed_at is not None` joins the `wrong_state` condition in `answer_mock_call`)**

- [ ] **Step 4: Run the whole suite** (the session fixture downgrades to base and upgrades, so the migration is proven both ways)

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions app/voice/models.py app/voice/service.py app/calls/mock.py tests
git commit -m "backend: calls.dialed_at; a dialed call is never canceled or carded (#47)"
```

---

### Task 3: Settle a call by Twilio's word; unanswered real calls redial

**Files:**
- Modify: `app/voice/service.py` (`transition` gains `only_from`; remove `machine_answered`, which this task leaves unused)
- Modify: `app/calls/ending.py` (new `settle`)
- Modify: `app/voice/router.py` (`status` and `amd` call `settle`)
- Test: `tests/calls/test_ending.py`, `tests/voice/test_voice.py`

**Interfaces:**
- Consumes: `voice.service.transition`, `calls.ending.conclude`, `twilio.hang_up` (Task 1).
- Produces:
  - `voice.service.transition(session, call_id, sid, new, *, only_from: CallState | None = None) -> CallState | None`: with `only_from`, moves nothing unless the locked row is in that state.
  - `calls.ending.settle(session, call_id: uuid.UUID, sid: str | None, new: CallState | None, *, only_from: CallState | None = None) -> CallState | None`: `transition`; if it moved the call to `unanswered` or `failed` and the trigger is not `welcome` or `test`, `conclude(session, call, None)`; commits; returns the move.

- [ ] **Step 1: Write the failing tests**

```python
async def test_no_answer_on_a_first_attempt_queues_the_redial(client, db, campaign_call):
    # status callback CallStatus=no-answer → call unanswered, one queued attempt=2 call due after redial_delay()

async def test_busy_on_a_second_attempt_ends_yellow(client, db, ...):
    # attempt=2 call, CallStatus=busy → final_severity yellow, reason "Nu a răspuns de două ori"

async def test_failed_counts_as_unanswered(client, db, campaign_call):
    # CallStatus=failed on a ringing first attempt → failed, redial queued

async def test_a_repeated_no_answer_queues_one_redial(client, db, campaign_call):
    # the same callback twice → exactly one attempt=2 row

async def test_voicemail_queues_the_redial_and_hangs_up(client, db, campaign_call, monkeypatch):
    # amd AnsweredBy=machine_start → unanswered, redial queued, hang_up called with the sid

async def test_welcome_and_test_calls_are_not_concluded(client, db, ...):
    # no-answer on a welcome call and on a test call → unanswered, no new row, no report

async def test_only_from_leaves_a_call_that_moved_on(db, campaign_call):
    # settle(..., CallState.failed, only_from=CallState.queued) on a ringing call → None, still ringing
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/calls/test_ending.py tests/voice/test_voice.py -q`
Expected: FAIL (no redial row; `settle` missing).

- [ ] **Step 3: Implement `only_from`, `settle`, and route `status`/`amd` through `settle`** (`amd`: `moved = await settle(..., CallState.unanswered)`; if `moved is CallState.unanswered and sid`, `hang_up(sid)` with the warning on `httpx.HTTPError` that `machine_answered` had)

- [ ] **Step 4: Run the suite and the contracts**

Run: `uv run pytest -q && uv run lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/voice app/calls tests
git commit -m "backend: unanswered real calls run the redial rule (#47, 06 §1)"
```

---

### Task 4: The stand-in welcome call

**Files:**
- Modify: `app/voice/dialogue.py` (`WELCOME_STANDIN` and `welcome_standin(form_of_address) -> Response`)
- Modify: `app/voice/router.py` (`POST /voice/welcome`)
- Test: `tests/voice/test_voice.py`

**Interfaces:**
- Consumes: `voice.service.move_call`, `form_of_address`.
- Produces: `POST /api/voice/welcome?call=<id>`, signed like every callback: moves the call to `completed`, answers TwiML `<Say language="ro-RO">…</Say><Hangup/>` with the sentence from Global Constraints; an unknown call or a database error answers `sorry()` as `/voice/answer` does.

- [ ] **Step 1: Write the failing tests**

```python
async def test_the_welcome_stand_in_speaks_and_hangs_up(client, db, welcome_call):
    r = await callback(client, "welcome", welcome_call.id, FIXTURES["answer"])
    assert r.status_code == 200
    assert "Acesta este un apel de test EchoCare." in r.text
    assert "Bună ziua, doamna Maria." in r.text
    assert r.text.rstrip().endswith("<Hangup/></Response>")
    assert (await stored(db, welcome_call)).state == "completed"

async def test_twilios_completed_leaves_the_stand_in_completed(client, db, welcome_call):
    # after /voice/welcome, a status callback CallStatus=completed → still completed, not dropped

async def test_the_welcome_stand_in_refuses_a_bad_signature(client, welcome_call):
    # sign=False → 403
```

- [ ] **Step 2: Run them to verify they fail** — `uv run pytest tests/voice/test_voice.py -q`, expected 404 on `/voice/welcome`.

- [ ] **Step 3: Implement the route and the dialogue helper**

- [ ] **Step 4: Run** `uv run pytest tests/voice -q` — PASS.

- [ ] **Step 5: Commit**

```bash
git add app/voice tests/voice
git commit -m "backend: stand-in welcome call speaks and hangs up (#47)"
```

---

### Task 5: The dialer; `place_call.py` follows the same rules

**Files:**
- Create: `app/scheduler/__init__.py` (empty), `app/scheduler/dialer.py`
- Modify: `app/voice/service.py` (`take_for_dialing`, `store_sid`)
- Modify: `pyproject.toml` (new top layer `"scheduler"` above `"calls | agent | system"`)
- Modify: `scripts/place_call.py`
- Test: `tests/scheduler/test_dialer.py`, `tests/tooling/test_scripts.py`

**Interfaces:**
- Consumes: Task 1's `configured`, `dial_allowed`, `dial(..., answer)`, `refused`; Task 3's `settle`.
- Produces:
  - `voice.service.take_for_dialing(session, call_id, now) -> bool`: sets `dialed_at = now` only if the row is still `queued` with `dialed_at IS NULL` (an `UPDATE … WHERE`); doesn't commit.
  - `voice.service.store_sid(session, call_id, sid) -> None`: sets `twilio_call_id` if still null; doesn't commit.
  - `scheduler.dialer.dial_due(now: datetime) -> int`: the number of calls handed to Twilio. Opens its own sessions.
- Selection, in one query: `state = queued`, `dialed_at IS NULL`, `due_at <= now`, trigger/enrollment by a dialer-local `DIALABLE = {campaign: active, watch: active, manual: active, welcome: accepted}` (a `test` call is `place_call.py`'s and never picked), `dial_allowed(senior.phone_e164)` applied in Python after the query, ordered by `Call.id`, limited to `max_live_calls` minus live calls with `dialed_at` set. Nothing at all when `not configured()`.
- Per call: `take_for_dialing` + commit → `dial(phone, id, "welcome" if welcome else "answer")` → `store_sid` + commit. `refused(e)` → `settle(session, id, None, CallState.failed)`. Any other `httpx.HTTPError` → log warning "outcome unknown", leave it.

- [ ] **Step 1: Write the failing tests** (patch `app.scheduler.dialer.dial`; set Twilio settings and `dial_allowlist="*"` with `monkeypatch.setattr(get_settings(), …)`)

```python
async def test_a_due_call_is_dialed_and_its_sid_stored(db, ...):
    # one due campaign call → dial_due returns 1; dialed_at set; twilio_call_id == "CA1"

async def test_a_call_not_yet_due_waits(db, ...): # due_at in the future → 0, dial not called

async def test_due_calls_go_in_id_order_up_to_the_free_lines(db, ...):
    # max_live_calls=3, one dialed live call, three due calls → the two lowest ids are dialed

async def test_a_dialed_call_is_never_dialed_again(db, ...):
    # dial_due twice; dial raises httpx.ReadTimeout the first time → called once in total;
    # the call stays queued, dialed_at set, no sid

async def test_without_twilio_nothing_is_dialed(db, ...):
    # twilio_account_sid="" → 0; GET /profile/mock-call still shows the call

async def test_the_allowlist_decides(db, ...):
    # dial_allowlist="" → 0; set to the senior's number → 1; another number → 0 and the card stays

async def test_twilio_refusing_fails_the_call_and_queues_the_redial(db, ...):
    # dial raises HTTPStatusError 400 → state failed, attempt=2 queued

async def test_a_welcome_call_answers_at_the_welcome_address(db, ...):
    # accepted senior's welcome call → dial called with answer="welcome"
```

```python
# tests/tooling/test_scripts.py
async def test_place_call_stamps_dialed_at_and_follows_the_allowlist(db, add_senior, monkeypatch):
    # allowlist empty → (False, message naming DIAL_ALLOWLIST), no call row
    # allowlisted, dial raises httpx.ReadTimeout → (False, "outcome unknown …"), call queued with dialed_at
```

- [ ] **Step 2: Run them to verify they fail** — `uv run pytest tests/scheduler tests/tooling -q`, expected `ModuleNotFoundError: app.scheduler`.

- [ ] **Step 3: Implement the two voice functions, `dial_due`, the layer entry and the script changes**

- [ ] **Step 4: Run** `uv run pytest -q && uv run lint-imports && uv run ruff check .` — PASS (`test_only_the_owner_writes_a_table` included).

- [ ] **Step 5: Commit**

```bash
git add app/scheduler app/voice/service.py pyproject.toml scripts/place_call.py tests
git commit -m "backend: dialer hands due calls to Twilio, up to MAX_LIVE_CALLS (#47)"
```

---

### Task 6: The sweep for stuck calls

**Files:**
- Create: `app/scheduler/sweep.py`
- Test: `tests/scheduler/test_sweep.py`

**Interfaces:**
- Consumes: `twilio.fetch_status`, `twilio.hang_up` (Task 1), `TWILIO_STATUSES` (`app/voice/calls.py`), `settle` with `only_from` (Task 3).
- Produces: `scheduler.sweep.STUCK_AFTER = timedelta(seconds=RING_SECONDS) + timedelta(minutes=3) + timedelta(minutes=1)`; `sweep(now: datetime) -> int`, the number of calls settled.
- Picks calls in `LIVE` with `dialed_at < now - STUCK_AFTER`. With a sid: `status = fetch_status(sid)`; if `status` is `queued`, `ringing` or `in-progress`, `hang_up(sid, status)` then `fetch_status` again; `settle(session, id, sid, TWILIO_STATUSES.get(status))`. Without a sid: `settle(session, id, None, CallState.failed, only_from=<state read>)`. Each settled call: `log.warning("swept call %s: %s -> %s (Twilio %s)", …)`. An `httpx.HTTPError` on one call is logged and the loop moves on.

- [ ] **Step 1: Write the failing tests** (patch `app.scheduler.sweep.fetch_status` / `hang_up`)

```python
async def test_a_call_stuck_in_progress_is_settled_from_twilio(db, ...):
    # in_progress, sid, dialed 5 min ago; Twilio "completed" → dropped; sweep returns 1

async def test_a_call_twilio_still_has_live_is_hung_up_first(db, ...):
    # fetch_status returns "in-progress" then "completed" → hang_up(sid, "in-progress") called, call dropped

async def test_a_call_stuck_ringing_without_a_sid_fails(db, ...):
    # ringing, no sid, dialed 5 min ago → failed; first campaign attempt → redial queued

async def test_a_call_inside_the_limit_is_left_alone(db, ...):
    # dialed 2 min ago → fetch_status not called, state unchanged

async def test_a_twilio_error_on_one_call_does_not_stop_the_sweep(db, ...):
    # two stuck calls; fetch_status raises for the first → the second is still settled
```

- [ ] **Step 2: Run to fail** — `uv run pytest tests/scheduler/test_sweep.py -q`.
- [ ] **Step 3: Implement `sweep`.**
- [ ] **Step 4: Run** `uv run pytest -q && uv run lint-imports` — PASS.
- [ ] **Step 5: Commit**

```bash
git add app/scheduler/sweep.py tests/scheduler/test_sweep.py
git commit -m "backend: sweep settles calls Twilio never reported on (#47)"
```

---

### Task 7: `POST /me/check-ins` and the watch silence step

**Files:**
- Modify: `app/seniors/schemas.py` (`CheckInForm`), `app/seniors/service.py`, `app/seniors/router.py`
- Test: `tests/seniors/test_check_ins.py`

**Interfaces:**
- Produces:
  - `CheckInForm`: `measured_at: AwareDatetime`, `battery: int | None = Field(None, ge=0, le=100)`, `worn: bool | None = None`, `last_pulse: int | None = Field(None, ge=0, le=300)`.
  - `seniors.service.record_check_in(session, senior_id, form, now) -> None`: upsert of `watch_states`; `measured_at` after `now` is stored as `now`; a stored `last_check_in_at` later than it changes nothing; `worn is False` → `not_worn`, else `ok`. Commits.
  - `seniors.service.watch_silence() -> timedelta`: 90 s with `demo_mode`, else 45 min.
  - `seniors.service.silence_watches(session, now) -> int`: `ok`/`not_worn` with `last_check_in_at < now - watch_silence()` → `offline`; logs the count; commits.
  - `POST /api/me/check-ins` → 204, `require_roles(Role.senior)`; the senior is the one the caller's `senior` grant names.

- [ ] **Step 1: Write the failing tests**

```python
async def test_a_first_check_in_creates_the_watch_state(client, db, add_active_senior): # 204, state ok, battery stored
async def test_not_worn(client, ...): # worn=False → not_worn
async def test_an_older_check_in_changes_nothing(client, ...): # second measured earlier → first kept
async def test_a_future_time_is_stored_as_arrival(client, ...): # measured_at = now+1h → last_check_in_at ≈ now
async def test_a_naive_time_is_422(client, ...): # "2026-10-24T10:00:00" → 422
async def test_only_a_senior_checks_in(client, add_user, ...): # a medic → 403 not_allowed
async def test_a_silent_watch_goes_offline_and_comes_back(db, client, ...):
    # last_check_in 50 min ago, demo_mode False → silence_watches returns 1, offline;
    # a check-in afterwards → ok
async def test_a_watch_inside_the_limit_stays(db, ...): # 30 min ago → 0
```

- [ ] **Step 2: Run to fail** — `uv run pytest tests/seniors/test_check_ins.py -q`, expected 404/405.
- [ ] **Step 3: Implement the schema, the three functions and the route.**
- [ ] **Step 4: Run** `uv run pytest -q && uv run lint-imports` — PASS.
- [ ] **Step 5: Commit**

```bash
git add app/seniors tests/seniors/test_check_ins.py
git commit -m "backend: POST /me/check-ins and watch silence (#47, UC-13)"
```

---

### Task 8: The loop in FastAPI's lifespan

**Files:**
- Create: `app/scheduler/loop.py`
- Modify: `app/main.py` (lifespan), `tests/conftest.py` (`os.environ["SCHEDULER_ENABLED"] = "false"` beside the other variables)
- Test: `tests/scheduler/test_loop.py`

**Interfaces:**
- Consumes: `campaigns.service.cancel_lapsed`, `dial_due`, `sweep`, `silence_watches`.
- Produces:
  - `scheduler.loop.LOCK = <a fixed 64-bit int, distinct from CAMPAIGN_LOCK>`; `TICK = 5` seconds.
  - `tick(now: datetime | None = None) -> bool`: False when another holder has the lock. Takes `pg_try_advisory_lock(LOCK)` on one `engine.connect()` connection held for the whole tick, runs the four steps in order (cancel lapsed in its own committed session), each in `try/except Exception: log.exception(...)`, then `pg_advisory_unlock`.
  - `run() -> None`: `while True: await tick(); await asyncio.sleep(TICK)`, with `log.exception` around `tick`.
  - `main.py`: a lifespan that starts `run()` as a task when `settings.scheduler_enabled`, and cancels it on shutdown.

- [ ] **Step 1: Write the failing tests**

```python
async def test_two_schedulers_one_tick(db, monkeypatch):
    # hold pg_advisory_lock(LOCK) on a separate connection → tick() is False and dial_due not called;
    # release it → tick() is True

async def test_a_step_that_raises_does_not_stop_the_others(db, monkeypatch):
    # patch dial_due to raise → tick() is True and sweep and silence_watches were still called

async def test_the_tick_cancels_a_lapsed_campaigns_calls(db, ...):
    # lapsed campaign with an undialed queued call → canceled after tick()

def test_the_lifespan_starts_no_loop_in_tests():
    # TestClient(app) enters and leaves the lifespan; patch run to record calls → not called
```

- [ ] **Step 2: Run to fail** — `uv run pytest tests/scheduler/test_loop.py -q`.
- [ ] **Step 3: Implement `loop.py` and the lifespan.**
- [ ] **Step 4: Run** `uv run pytest -q && uv run lint-imports && uv run ruff check . && uv run ruff format --check .` — PASS.
- [ ] **Step 5: Commit**

```bash
git add app/scheduler/loop.py app/main.py tests
git commit -m "backend: scheduler loop in the lifespan, one copy by advisory lock (#47, G9)"
```

---

### Task 9: Spec, README and agent guide

**Files:**
- Modify: `../docs/specs/echocare/06-operations.md` (§1 restart and deploy rows; §2 flowchart: lock → cancel lapsed → dial → sweep → watch silence, home node steps kept as proposed; §3 add "sweep: a dialed call unsettled after ring + call limit + 1 min"; §4 Twilio processes calls in IE1, the number is Romanian, and "Honest limits")
- Modify: `../docs/specs/echocare/04-interfaces.md` (§2 lapsed-warning paragraph: on the tick, lazy as fallback; mock-call rows: a dialed call is refused `wrong_state`; §3 check-in body and 204; §4.1 the IE1 host; §4.2 a stand-in welcome row, voicemail and no-answer run the redial rule)
- Modify: `../docs/specs/echocare/05-data-model.md` (`dialed_at` on call)
- Modify: `README.md` (backend: real calls locally — Twilio variables, IE1 token and host, `cloudflared tunnel --url http://localhost:8000`, `PUBLIC_BASE_URL`, restart after a new tunnel address, `DIAL_ALLOWLIST`, replace the seeded numbers by hand), `AGENTS.md` (layout: `scheduler/`)
- Modify: `app/campaigns/service.py` (`cancel_lapsed` docstring: the scheduler runs it; the endpoints keep it as a fallback)

- [ ] **Step 1: Make the edits.** Each claim matches the code of Tasks 1–8; cite IDs.
- [ ] **Step 2: Run** `uv run pytest -q && uv run ruff check .` — PASS.
- [ ] **Step 3: Commit**

```bash
git add ../docs/specs/echocare README.md AGENTS.md app/campaigns/service.py
git commit -m "docs: scheduler, dialer, check-ins and IE1 in the spec (#47)"
```

---

### Task 10: Done when (human, on the local stack)

- [ ] **Step 1:** With Task 1's checkpoint settings, `DIAL_ALLOWLIST=<their mobile>`, and a senior in `submitted` whose number is that mobile: `docker compose up --watch`, accept the senior on the dashboard. Passed when the phone rings within ~10 s without `place_call.py`, says the stand-in sentence and hangs up; the call is `completed`.
- [ ] **Step 2:** Make that senior `active` (by hand in the database, since the stand-in gives no consent) and start a campaign; answer, then stop the tunnel mid-call. Passed when, about 4.5 minutes after the dial, `docker compose logs api` shows `swept call … (Twilio completed)` and the call is no longer live.
