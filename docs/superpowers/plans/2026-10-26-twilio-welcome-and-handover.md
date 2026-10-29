# Real Welcome and Wellbeing Calls, and the Hand-over Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The welcome call records consent by key or voice, a wellbeing call greets by trigger over ConversationRelay, and key 9 or a tier 1 phrase hands the call to the on-duty DAS phone, whose answer takes the incident (issue #48).

**Architecture:**
- The welcome call is a TwiML `<Gather>` script answered by three signed callbacks in `voice/router.py`. Its endings go through `calls/ending.py`, which composes the `seniors`, `codes` and `voice` writers (ADR-005).
- A wellbeing call's relay session gets a hand-over function from the router, because `agent` may import only `voice` and `status`. That function writes the report, the code, the incident and `handed_over` before the session sends `end`.
- Three more signed callbacks (`/voice/handoff`, `-answered`, `-result`) dial and bridge the on-duty phone.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async + asyncpg, httpx, pytest (asyncio auto), import-linter. No migration.

**Spec:** [docs/superpowers/specs/2026-10-26-twilio-welcome-and-handover-design.md](../specs/2026-10-26-twilio-welcome-and-handover-design.md)

## Global Constraints

- Commands run from `backend/`. Tests `uv run pytest`; lint `uv run ruff check .`, `uv run ruff format --check .`, `uv run lint-imports`. All pass at every commit (lefthook runs them; never `--no-verify`).
- No migration: `calls.welcome_outcome`, `calls.handover_answered`, `consents.evidence` and the states `wrong_number`, `unreachable`, `handed_over` exist.
- Only a table's owner writes it (ADR-005): `calls` → `app/voice/service.py`; `seniors`, `consents` → `app/seniors/service.py`; `incidents` → `app/incidents/service.py`; codes and reports → `app/codes/service.py`. `test_only_the_owner_writes_a_table` enforces it.
- `agent` imports only `voice` and `status`. Routers may import anything. Import a name from the module that defines it; no imports inside functions.
- Every new callback depends on `twilio_params` (signed, 403 otherwise). A failure answers `sorry()`, never Twilio's English error.
- Tests and fixtures use `+40700000xxx` numbers only. No real number in code, tests, fixtures, docs or commit messages.
- Values:
  - redial delay `redial_delay()`: 20 min, 20 s in demo mode;
  - on-duty ring time: 30 s, 15 s in demo mode;
  - consent text version `"v1"` (`CONSENT_VERSION`), method `ConsentMethod.call`;
  - `<Say>` voice `f"{TWILIO_TTS_PROVIDER}.{TWILIO_VOICE}"`, `language="ro-RO"`.
- Speech matches are made on `app.status.alarms.normalize(text)`:
  - identity yes: `{"da"}`;
  - consent yes: `{"da", "sunt de acord", "da sunt de acord"}`;
  - consent no: `{"nu", "nu sunt de acord"}`.
- Romanian text, exact:
  - Identity: `Bună ziua. Sunt asistentul automat al DAS Timișoara. Vorbesc cu {f}? Dacă da, apăsați 1 sau spuneți «da». Dacă {f} nu poate veni acum la telefon, apăsați 2. Dacă ați primit acest apel din greșeală, apăsați 3.`
  - Repeat prefix: `Nu v-am auzit.`
  - Given: `Vă mulțumim. Vă rugăm să salvați acest număr. Nu vă vom cere niciodată bani sau date. La revedere.`
  - Refused: `Am înțeles. Vă rugăm să salvați acest număr. Nu vă vom cere niciodată bani sau date. La revedere.`
  - Not available: `Vă mulțumim. Vom suna din nou mai târziu. La revedere.`
  - Wrong number: `Ne cerem scuze pentru deranj. La revedere.`
  - Silent twice: `Nu v-am auzit. La revedere.`
  - Unclear twice: `Nu v-am înțeles. La revedere.`
  - Connecting: `Vă conectez acum cu un operator, rămâneți pe fir.`
  - Call back: `Un coleg vă va suna înapoi în cel mai scurt timp.`
  - Self-harm: the existing `SELF_HARM_HANDOVER`.
- Greetings, where `{f}` is the form of address:
  - campaign: `Bună ziua, {f}. Sunt asistentul DAS Timișoara. Vă sun pentru că azi e cod {galben|roșu} de {ger|caniculă}. Nu vă cer niciodată bani sau date. Cum vă simțiți azi?`
  - watch: `Bună ziua, {f}. Sunt asistentul DAS Timișoara. Vă sun pentru că ceasul a semnalat ceva neobișnuit. Nu vă cer niciodată bani sau date. Cum vă simțiți?`
  - manual: the same, with `Vă sun pentru că ați cerut să vorbim.`
  - test: the existing `greeting()`.
- Reasons: tier 1 `A spus: «{words}»`, cut to 200 characters (`Call.reason`); key 9 `A cerut un operator (tasta 9)`.

## Review Focus

- **Twilio repeats a `<Gather>` action** (a retry after a slow answer): a second request finds the call already `completed`. It records no second consent and queues no second retry, and answers a polite hang-up. Test in Task 2.
- **The senior hangs up partway through the welcome script:** Twilio's `completed` makes the call `dropped`, and the retry rule runs as for silence. Test in Task 1.
- **Speech as people say it** („Da.”, „DA!”, „Sunt de acord.”, „da, sunt de acord”): matched after normalization. „Da, cred” is not a consent. Test in Task 2.
- **Key 9 or „am căzut” on a `place_call.py` test call:** echoed, no hand-over, nothing written. Test in Task 4.
- **`HandoffData` that isn't JSON, or names another call:** hang up, nothing dialed. Test in Task 5.

---

### Task 1: Welcome endings in the domain

**Files:**
- Modify: `app/seniors/service.py` (`confirm_welcome`; new `end_welcome`)
- Modify: `app/calls/ending.py` (`conclude_welcome`; new `retry_welcome`, `close_welcome`; `settle` for welcome calls)
- Test: `tests/calls/test_ending.py`, `tests/seniors/` (where `confirm_welcome` is tested today)

**Interfaces:**
- Produces:
  - `seniors.service.confirm_welcome(session, senior_id, call_id, *, given, method, text_version, evidence: dict[str, Any] | None = None) -> bool`. It stores `evidence` on the `Consent`.
  - `seniors.service.end_welcome(session, senior_id, state: EnrollmentState) -> bool`. It moves `accepted` → `state` (`wrong_number` or `unreachable`) with the same guarded `update … returning` as `confirm_welcome`, and returns False when the senior is no longer `accepted`. Doesn't commit.
  - `calls.ending.conclude_welcome(session, call, *, given, method, text_version, evidence: dict[str, Any] | None = None) -> bool`. It passes `evidence` through.
  - `calls.ending.retry_welcome(session, call: Call) -> None`. It runs on an already-ended welcome call: attempt 1 → `queue_redial(session, call, now + redial_delay())`; attempt ≥ 2 → `end_welcome(…, EnrollmentState.unreachable)`. Doesn't commit.
  - `calls.ending.close_welcome(session, call: Call, outcome: WelcomeOutcome) -> bool`. A call that is not `in_progress` → False, nothing written. Otherwise `finish(call, completed, welcome_outcome=outcome)`, then:
    - `wrong_number` → `end_welcome(…, wrong_number)`;
    - anything else → `retry_welcome`.

    Doesn't commit.
  - `settle`: a `welcome` call that this move ended `unanswered`, `failed` or `dropped` gets `welcome_outcome = no_answer`, then `retry_welcome`. `test` calls are still never concluded.

- [ ] **Step 1: Write the failing tests**

```python
async def test_a_call_consent_keeps_its_evidence(db, ...):
    # conclude_welcome(given=True, method=call, text_version="v1",
    #   evidence={"digits": "1"}) → Consent.evidence == {"digits": "1"}, senior active, code green

async def test_wrong_number_ends_the_welcome(db, ...):
    # in_progress welcome call; close_welcome(…, WelcomeOutcome.wrong_number) is True
    # → call completed, welcome_outcome wrong_number, senior wrong_number, no call queued

@pytest.mark.parametrize("outcome", ["not_available", "no_answer", "confirmed"])
async def test_a_first_welcome_that_gets_nowhere_is_retried(db, outcome, ...):
    # attempt 1 → a queued welcome call, attempt 2, previous_call_id set,
    # due ≈ now + redial_delay(); senior still accepted

async def test_a_second_welcome_that_gets_nowhere_makes_the_senior_unreachable(db, ...):
    # attempt 2, close_welcome(no_answer) → senior unreachable, nothing queued

async def test_closing_an_ended_welcome_changes_nothing(db, ...):
    # call already completed → close_welcome returns False, no second retry queued

async def test_a_withdrawn_senior_is_left_as_they_are(db, ...):
    # senior withdrawn mid-call; attempt 2 close_welcome → senior still withdrawn

@pytest.mark.parametrize("status", ["no-answer", "failed", "completed"])  # completed → dropped
async def test_a_welcome_twilio_ends_runs_the_retry_rule(client, db, status, ...):
    # POST /voice/status for a live welcome call → welcome_outcome no_answer, attempt 2 queued

async def test_a_test_call_is_still_never_concluded(client, db, ...):
    # trigger test, no-answer → nothing queued
```

Remove or update the existing tests that assert welcome calls are moved but never concluded.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/calls/test_ending.py -v`
Expected: FAIL (`ImportError` for `close_welcome`, `end_welcome`; unexpected `evidence` keyword).

- [ ] **Step 3: Implement the functions above**

In `close_welcome`, `finish` runs before `queue_redial`, both in the same session: the retry must never meet a live call for the senior (`uq_calls_live_senior`, 05 §3).

- [ ] **Step 4: Run the tests and lint**

Run: `uv run pytest tests/calls tests/seniors tests/voice -q && uv run ruff check . && uv run lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/seniors/service.py app/calls/ending.py tests/calls tests/seniors tests/voice
git commit -m "backend: welcome endings, retry and unreachable in the domain (#48)"
```

---

### Task 2: The welcome call's script and callbacks

**Files:**
- Create: `app/voice/welcome.py` (the script's text and the answer parsers)
- Modify: `app/voice/dialogue.py` (`<Say>` with the voice, `<Gather>` builder), `app/voice/twilio.py` (`voice_url` extra query), `app/voice/router.py`
- Test: `tests/voice/test_welcome.py` (new); remove the stand-in tests from `tests/voice/test_voice.py`

**Interfaces:**
- Consumes: Task 1's `conclude_welcome`, `close_welcome`.
- Produces:
  - `twilio.voice_url(path: str, call_id: uuid.UUID, scheme: str | None = None, **params: str) -> str`. It appends `&name=value` after `call=<id>`, in the order given.
  - `dialogue.say(text: str) -> str`: a `<Say>` element with `language` and `voice` from settings, text escaped. `sorry()` uses it. `welcome_standin` and `WELCOME_STANDIN` are deleted.
  - `dialogue.gather(action: str, text: str) -> Response`: `<Gather input="dtmf speech" numDigits="1" language="ro-RO" actionOnEmptyResult="true" action=… method="POST">` wrapping `say(text)`.
  - `dialogue.say_and_hang_up(text: str) -> Response`.
  - `welcome.identity(form_of_address: str) -> str`.
  - `welcome.NOT_HEARD`, and the six ending sentences as constants: `GIVEN`, `REFUSED`, `NOT_AVAILABLE`, `WRONG_NUMBER`, `SILENT`, `UNCLEAR`.
  - `welcome.identity_answer(digits: str, speech: str) -> WelcomeOutcome | None`:
    - `"1"` or speech „da” → `confirmed`;
    - `"2"` → `not_available`;
    - `"3"` → `wrong_number`;
    - anything else → None.
  - `welcome.consent_answer(digits: str, speech: str) -> bool | None`: True given, False refused, None unclear. Key `"0"` is handled by the router before this.
  - `welcome.evidence(params: dict[str, str]) -> dict[str, Any]`: `{"digits": …}` or `{"speech": …, "confidence": float}`.
  - Routes, each `?call=<id>&try=<1|2>` where it repeats:
    - `POST /voice/welcome` (also reached from `/voice/answer` for a welcome trigger in Task 3);
    - `POST /voice/welcome/identity`;
    - `POST /voice/welcome/consent`.

- [ ] **Step 1: Write the failing tests**

Extend the `callback` helper with `query=""` appended to the signed and the posted address.

```python
async def test_pickup_asks_who_answers(client, db, welcome_call):
    # POST /voice/welcome → <Gather … action=".../welcome/identity?call=<id>&try=1">,
    # identity text with "doamna Maria" twice, voice "Google.ro-RO-Wavenet-A"; call in_progress

@pytest.mark.parametrize("params", [{"Digits": "1"}, {"SpeechResult": "Da.", "Confidence": "0.91"}])
async def test_yes_at_identity_asks_for_consent(client, welcome_call, params):
    # → <Gather action=".../welcome/consent?call=<id>&try=1"> with CONSENT_TEXT

async def test_silence_at_identity_asks_again_then_says_goodbye(client, db, welcome_call):
    # try=1 empty → NOT_HEARD + identity, action try=2; try=2 empty → SILENT, <Hangup/>,
    # welcome_outcome no_answer, a retry queued

@pytest.mark.parametrize("digits, outcome, state", [("2", "not_available", "accepted"), ("3", "wrong_number", "wrong_number")])
async def test_identity_keys(client, db, welcome_call, digits, outcome, state):
    ...

@pytest.mark.parametrize("params", [
    {"Digits": "1"}, {"SpeechResult": "DA!"}, {"SpeechResult": "Sunt de acord."},
    {"SpeechResult": "da, sunt de acord"},
])
async def test_consent_given(client, db, welcome_call, params):
    # → GIVEN, <Hangup/>; senior active, code green; Consent method call, version v1, evidence kept

@pytest.mark.parametrize("params", [{"Digits": "2"}, {"SpeechResult": "Nu."}])
async def test_consent_refused(client, db, welcome_call, params):
    # → REFUSED; senior refused

async def test_key_0_reads_the_consent_again_without_counting(client, welcome_call):
    # try=1 Digits=0 → consent Gather still try=1

async def test_a_maybe_is_not_a_consent(client, db, welcome_call):
    # SpeechResult "Da, cred" try=1 → asked again (try=2); try=2 → UNCLEAR, retry queued, senior accepted

async def test_a_repeated_gather_action_records_nothing_twice(client, db, welcome_call):
    # consent Digits=1 posted twice → one Consent row; second answer is a polite <Hangup/>

async def test_a_gather_for_an_ended_call_hangs_up(client, db, welcome_call):
    # call completed → identity Digits=1 → <Hangup/>, nothing written

@pytest.mark.parametrize("path", ["welcome", "welcome/identity", "welcome/consent"])
async def test_welcome_callbacks_refuse_a_bad_signature(client, welcome_call, path):
    # sign=False → 403
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/voice/test_welcome.py -v`
Expected: FAIL (404 for the new routes; `ImportError` for `app.voice.welcome`).

- [ ] **Step 3: Implement `app/voice/welcome.py`, the `dialogue` builders, `voice_url`'s params and the three routes**

`/voice/welcome` moves the call to `in_progress` through `move_call` before answering. A route that finds the call no longer `in_progress` answers `say_and_hang_up` with nothing written. Database errors answer `sorry()`, as `answer` does today.

- [ ] **Step 4: Run the tests and lint**

Run: `uv run pytest tests/voice -q && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/voice tests/voice
git commit -m "backend: the welcome call asks identity and consent by key or voice (#48, UC-04)"
```

---

### Task 3: Answer by trigger; the wellbeing greeting and the hand-over address

**Files:**
- Modify: `app/calls/service.py` (new `answer_context`), `app/voice/dialogue.py` (new `wellbeing_greeting`), `app/voice/router.py` (`answer`, `relay`), `app/agent/session.py` (`serve` takes the greeting)
- Test: `tests/voice/test_voice.py`, `tests/calls/` (or `tests/voice/`) for `answer_context`

**Interfaces:**
- Consumes: Task 2's welcome pickup handler (the answer delegates to it for a welcome trigger).
- Produces:
  - `dialogue.wellbeing_greeting(form_of_address: str, trigger: str, kind: str | None = None, level: str | None = None) -> str`. It takes plain strings, because `voice` cannot import `campaigns`. A `test` trigger returns the existing `greeting(form_of_address)`.
  - `calls.service.AnswerContext`: a frozen dataclass with `trigger: CallTrigger`, `form_of_address: str`, `greeting: str`.
  - `calls.service.answer_context(session, call_id) -> AnswerContext | None`. It joins `seniors` and, for a campaign, `campaigns`.
  - `agent.session.serve(ws, call: uuid.UUID, greeting: str, hand_over: HandOver | None = None) -> None`. `HandOver` is defined in Task 4; until then the argument is unused.
  - `/voice/answer`:
    - welcome trigger → the welcome pickup;
    - otherwise `<Connect action="{voice_url('handoff', call)}"><ConversationRelay … welcomeGreeting=answer_context.greeting/></Connect>`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_a_welcome_call_answered_at_answer_gets_the_welcome(client, welcome_call):
    # POST /voice/answer → identity <Gather>

async def test_a_campaign_call_greets_with_its_warning(client, db, add_senior):
    # cold, red campaign call → welcomeGreeting contains "azi e cod roșu de ger"
    # and <Connect action="https://echocare.test/api/voice/handoff?call=<id>">

@pytest.mark.parametrize("trigger, words", [("watch", "ceasul a semnalat"), ("manual", "ați cerut să vorbim")])
async def test_wellbeing_greetings(client, db, add_senior, trigger, words): ...

async def test_a_test_call_keeps_the_s1_greeting(client, db, add_senior): ...

async def test_the_transcript_opens_with_the_same_greeting(client, db, call):
    # relay setup stores turn 0 == the welcomeGreeting the answer sent
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/voice/test_voice.py -v`
Expected: FAIL (no `action` on `<Connect>`; S1 greeting on a campaign call).

- [ ] **Step 3: Implement `answer_context`, `wellbeing_greeting`, the two route changes and `serve`'s greeting**

The relay route opens a `Session()` for `answer_context` before calling `serve`, since `agent` holds no session. An unknown or ended call still closes the socket with 1008, as `open_line` decides.

- [ ] **Step 4: Run the tests and lint**

Run: `uv run pytest tests/voice tests/agent tests/calls -q && uv run ruff check . && uv run lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/calls/service.py app/voice app/agent tests
git commit -m "backend: answer by trigger; wellbeing greeting and the hand-over address (#48, 04 §4.2)"
```

---

### Task 4: Starting a hand-over from key 9 or a tier 1 phrase

**Files:**
- Modify: `app/voice/service.py` (new `live_call_for_update`), `app/calls/ending.py` (new `begin_handover`), `app/agent/relay.py`, `app/agent/session.py`, `app/voice/router.py` (the adapter)
- Test: `tests/calls/test_ending.py`, `tests/agent/test_relay.py`, `tests/voice/test_voice.py`

**Interfaces:**
- Consumes: Task 3's `serve(ws, call, greeting, hand_over)` and `AnswerContext.trigger`.
- Produces:
  - `voice.service.live_call_for_update(session, call_id) -> Call | None`: the row locked `FOR UPDATE`, or None unless `in_progress`.
  - `calls.ending.begin_handover(call_id: uuid.UUID, source: ReportSource, reason: str) -> bool`. It owns its session and commits, like `voice.service.save_turn`. It returns False when the call is not `in_progress`. Otherwise, in one transaction:
    1. `add_report(source, severity, reason)`, with severity red for `alarm_tier1` and yellow for `request_human`;
    2. the code: `max(severity, current)`, through `next_code`, so it never lowers;
    3. `open_incident(...)`, unless the senior has an unresolved incident, which is joined;
    4. `finish(call, handed_over, final_severity=…, reason=reason)`.
  - `agent.relay.Escalation(StrEnum)`: `alarm = "alarm"`, `key_9 = "key_9"`.
  - `agent.relay.HandOver = Callable[[Escalation, str], Awaitable[bool]]`. The second argument is the senior's words, or `""` for key 9.
  - `agent.relay.CONNECTING`, the connecting sentence.
  - `Relay(greeting, store, hand_over: HandOver | None = None)`. On `dtmf` `"9"`, or a `prompt` whose `alarms.check` match is `Tier.one`, when `hand_over` is set and returns True, the relay replies:
    1. `text` with `CONNECTING`, or `SELF_HARM_HANDOVER` for condition `self_harm`;
    2. `{"type": "end", "handoffData": json.dumps({"call": str(call_id), "reason": escalation})}`.

    When `hand_over` returns False it replies nothing. When `hand_over` is None (a test call), the relay echoes as today.
  - `serve` calls `end_completed` only for an `end` without `handoffData`.
  - The router builds the `HandOver` for a non-`test` call. It maps `alarm` → (`alarm_tier1`, `A spus: «{words}»`[:200]) and `key_9` → (`request_human`, `A cerut un operator (tasta 9)`).

- [ ] **Step 1: Write the failing tests**

```python
async def test_key_9_on_a_green_senior(db, ...):
    # begin_handover(call, request_human, reason) is True → code yellow, a request_human report,
    # one open incident opened_by this call, call handed_over with final_severity yellow

async def test_key_9_on_a_red_senior_joins_the_incident(db, ...):
    # red code and an open incident → code red, still one incident

async def test_tier_1_makes_red_and_opens_an_incident(db, ...): ...

async def test_a_second_hand_over_is_a_no_op(db, ...):
    # second begin_handover returns False; one report, one incident

# tests/agent/test_relay.py, scripted, hand_over a recording stub returning True
async def test_key_9_hands_over(): # replies [text CONNECTING, end with handoffData {"call", "reason": "key_9"}]
async def test_a_tier_1_phrase_hands_over(): # "am căzut și nu mă pot ridica" → reason "alarm"
async def test_self_harm_speaks_its_own_line(): # SELF_HARM_HANDOVER
async def test_a_negated_phrase_is_echoed(): # "nu am căzut" → heard(...), hand_over not called
async def test_a_tier_2_phrase_is_echoed(): # "am leșinat" → heard(...)
async def test_without_hand_over_key_9_is_echoed(): # hand_over None → "Ați apăsat tasta 9."

# tests/voice/test_voice.py, through voice_router.relay
async def test_key_9_on_a_wellbeing_call_ends_handed_over(client, db, call):
    # answered manual call, Socket [SETUP, dtmf 9] → state handed_over, an incident, last sent is end with handoffData;
    # Twilio's completed afterwards leaves handed_over

async def test_key_9_on_a_test_call_writes_nothing(client, db, add_senior):
    # trigger test → echoed, no incident, no report, state still in_progress
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/agent tests/calls/test_ending.py tests/voice/test_voice.py -v`
Expected: FAIL (`ImportError` for `begin_handover`, `Escalation`).

- [ ] **Step 3: Implement the functions above, the relay's two branches and the router's adapter**

The relay learns its call id from `serve`. Pass it to `Relay` as a keyword, or build `handoffData` in `serve`. The builder's choice; the reply's shape is fixed above.

- [ ] **Step 4: Run the tests and lint**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS, including `test_only_the_owner_writes_a_table` and the layers contract.

- [ ] **Step 5: Commit**

```bash
git add app/voice/service.py app/calls/ending.py app/agent app/voice/router.py tests
git commit -m "backend: key 9 and tier 1 phrases start a hand-over with its incident (#48, UC-07)"
```

---

### Task 5: The hand-over callbacks

**Files:**
- Modify: `app/auth/service.py` (new `on_duty`), `app/incidents/service.py` (new `take_for_handover`), `app/voice/service.py` (new `answer_handover`), `app/voice/twilio.py` (new `handover_ring_seconds`), `app/voice/dialogue.py` (`dial_on_duty`, `hang_up`, `CALL_BACK`), `app/voice/router.py`
- Test: `tests/voice/test_handover.py` (new)

**Interfaces:**
- Consumes: Task 3's `<Connect action>` address; Task 4's `handed_over` call and its incident.
- Produces:
  - `auth.service.on_duty(session) -> tuple[uuid.UUID, str] | None`: the on-duty DAS user's id and `phone_e164`.
  - `incidents.service.take_for_handover(session, senior_id, user_id) -> bool`. It moves the senior's `open` incident → `in_progress`, taken by `user_id`, and returns False if there is none open. It never raises and doesn't commit.
  - `voice.service.answer_handover(session, call_id, answered: bool) -> Call | None`. True always sets `handover_answered`; False sets it only while it is None. Doesn't commit.
  - `twilio.handover_ring_seconds() -> int`: 30, or 15 when `demo_mode`.
  - `dialogue.CALL_BACK`; `dialogue.hang_up() -> Response`.
  - `dialogue.dial_on_duty(number: str, *, ring: int, result_url: str, answered_url: str) -> Response`: `<Dial callerId=TWILIO_FROM_NUMBER timeout=ring action=result_url method="POST"><Number url=answered_url method="POST">number</Number></Dial>`.
  - `POST /voice/handoff`:
    - no `HandoffData`, data that isn't JSON, or data whose `call` isn't this call → `hang_up()`;
    - nobody on duty, or the number not `dial_allowed` → `say_and_hang_up(CALL_BACK)`, logged with the number masked;
    - otherwise `dial_on_duty` to `voice_url("handoff-result", call)` and `voice_url("handoff-answered", call, user=str(user_id))`.
  - `POST /voice/handoff-answered?call=&user=`: `answer_handover(True)`, `take_for_handover(senior, user)`, commit, empty `<Response/>`.
  - `POST /voice/handoff-result`:
    - `DialCallStatus` `completed` → `hang_up()`;
    - otherwise `answer_handover(False)`, commit, `say_and_hang_up(CALL_BACK)`.

- [ ] **Step 1: Write the failing tests**

```python
HANDOFF = {"HandoffData": json.dumps({"call": "<id>", "reason": "key_9"})}  # id filled per test

async def test_nobody_on_duty_hears_the_call_back_line(client, handed_over): # CALL_BACK + <Hangup/>
async def test_the_on_duty_phone_is_dialed(client, handed_over, on_duty_das, allow, monkeypatch):
    # settings twilio_from_number monkeypatched to "+15005550006" (conftest sets none)
    # <Dial callerId="+15005550006" timeout=str(handover_ring_seconds())
    #   action=".../handoff-result?call=<id>"><Number url=".../handoff-answered?call=<id>&user=<das id>">+40700000001</Number>
async def test_an_on_duty_number_off_the_allowlist_is_not_dialed(client, handed_over, on_duty_das): # CALL_BACK
@pytest.mark.parametrize("data", [None, "not json", json.dumps({"call": str(uuid.uuid4())})])
async def test_no_usable_handoff_data_hangs_up(client, handed_over, data): # <Hangup/>, no <Dial>
async def test_answering_takes_the_incident(client, db, handed_over, on_duty_das):
    # → incident in_progress, taken_by das; call handover_answered True; body "<Response></Response>"
async def test_an_incident_already_taken_stays_theirs(client, db, handed_over, on_duty_das, other_das): ...
async def test_no_answer_says_someone_will_call_back(client, db, handed_over):
    # DialCallStatus no-answer → CALL_BACK; handover_answered False; incident still open
async def test_a_completed_dial_hangs_up(client, db, handed_over): ...
@pytest.mark.parametrize("path", ["handoff", "handoff-answered", "handoff-result"])
async def test_handoff_callbacks_refuse_a_bad_signature(client, handed_over, path): # 403
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/voice/test_handover.py -v`
Expected: FAIL (404 for the routes).

- [ ] **Step 3: Implement the functions and the three routes**

- [ ] **Step 4: Run the whole suite and lint**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/auth/service.py app/incidents/service.py app/voice tests/voice/test_handover.py
git commit -m "backend: the hand-over dials the on-duty phone, and answering takes the incident (#48, 04 §4.4)"
```

---

### Task 6: Checkpoint (human): the live runs, recorded callbacks and S3

**Files:**
- Modify: `tests/voice/fixtures/twilio_callbacks.json` (recorded bodies, new keys `welcome_identity`, `welcome_consent`, `handoff`, `handoff_answered`, `handoff_result`), the tests from Tasks 2 and 5 that build bodies inline, which now read them from the fixtures

- [ ] **Step 1: Set up the local cast (local database and `backend/.env` only)**
  - Give a test senior the senior's number, and make them `submitted`.
  - Grant DAS to the DAS number (`grant_das.py`) and put them on duty (`PUT /api/staff/on-duty`).
  - Put both numbers on `DIAL_ALLOWLIST` and recreate the API container.

  None of these numbers goes into a file under Git.
- [ ] **Step 2: Run the three "Done when" scenarios**
  - Accept the senior and press 1, 1: the senior becomes `active` and green.
  - Run a manual call where the senior presses 9: the DAS phone rings, and answering shows the incident taken on the dashboard.
  - Run a manual call where the senior says „am căzut”: the code goes red, and the DAS phone rings.

  Passed when each matches. Stop and report on any 403 or English error voice.
- [ ] **Step 3: S3.** About ten „da” and ten „nu” on the consent question, from the senior's phone. Record how many each came back right, with Twilio's `Confidence`. If either misses more than twice, stop and ask whether the welcome goes keys only.
- [ ] **Step 4: Record the bodies.** Read `http://127.0.0.1:4040/api/requests/http` and take one request per callback path. Replace:
  - every `+40…` number with `+40700000101` (senior), `+40700000001` (DAS) or `+15005550006` (from);
  - `CA…`, `AC…` and `KA…` ids with placeholders of the same length.

  Save them over the fixtures with the new keys. Run `grep -E '\+40(7[0-9]{8})' tests/voice/fixtures/twilio_callbacks.json` and check that only `+407000001xx` and `+407000000xx` appear.
- [ ] **Step 5: Point the inline bodies of Tasks 2 and 5 at the fixtures, and run the suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/voice
git commit -m "backend: recorded Twilio callbacks for welcome and hand-over (#48, S1)"
```

---

### Task 7: Spec and README

**Files:**
- Modify: `docs/specs/echocare/README.md` (G16), `02-use-cases.md` (UC-04, UC-07), `03-status-model.md` (incident rule, §10 example 9), `04-interfaces.md` (§4.2 answer, welcome and hand-over rows; §4.3 key 9 and tier 1; §4.4 step 5 `<Number url>`), `05-data-model.md` (incident opening, `consents.evidence` for method `call`), `06-operations.md` (§6 S1 and S3 answers with today's date), `backend/README.md` ("Real calls locally" step 4)

- [ ] **Step 1: Make each change design §7 lists, citing #48**
- [ ] **Step 2: Check no real number entered the change**

Run: `git diff main... | grep -nE '\+40 ?7[0-9]{2} ?[0-9]{3} ?[0-9]{3}' | grep -vE '\+40700000'`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add docs/specs/echocare backend/README.md
git commit -m "docs: real welcome call, hand-over and its incident, S1 and S3 answers (#48)"
```
