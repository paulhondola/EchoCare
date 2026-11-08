# Agent Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the wellbeing call's echo with a Romanian conversation driven by DeepSeek-V4-Pro on DeepInfra. The model records answers through four tools, and the server's rules decide the code.

**Architecture:** `app/agent/` gets the pure tool rules (`tools.py`), the provider client (`model.py`), the instructions (`prompt.py`) and the session state machine (`loop.py`). The state machine runs each turn as a cancellable task and talks to the database only through a `Line` of callables that `voice/router.py` builds. `calls/ending.py` learns to conclude dropped calls from stored answers and concerns, and to hand over with a source-dependent severity. Test calls keep the S1 echo.

**Tech Stack:** Python 3.14, FastAPI, asyncio, SQLAlchemy async, `openai` SDK against `https://api.deepinfra.com/v1/openai`, pytest (asyncio auto mode), uv.

**Spec:** [docs/superpowers/specs/2026-11-08-agent-loop-design.md](../specs/2026-11-08-agent-loop-design.md). The design cites `docs/specs/echocare/` 04 §4.3–§5, 03 §3–§6 and 06 §3. Read the design before any task.

## Global Constraints

- Work on branch `49-agent-loop`. Run every command from `backend/` unless a step says otherwise. Commit with the lefthook hooks on; never `--no-verify`.
- `app.agent` imports only `app.voice`, `app.status` and external packages (import-linter contract "The agent talks only to voice"). It holds no database session. `uv run lint-imports` must pass after every task.
- Only a table's owner writes it (ADR-005): `answers` through `app.voice.service`, `status_reports` through `app.codes.service.add_report`.
- Everything in the request path is async (01 §8).
- New user-facing strings are Romanian; code, comments and docs English. Comments cite the spec by ID (`04 §5`, `03 §6`).
- Model request, exactly: `stream=True`, `temperature=0.3`, `max_tokens=1000`, `extra_body={"reasoning_effort": "none"}`, `tools=TOOLS`, base URL `https://api.deepinfra.com/v1/openai`.
- Limits, exactly: 3 model rounds per turn; 10 s to the first streamed item; 8 s tier 2 wait; 180 s call length limit; 2 re-asks per unclear question.
- Hand-over data reason: `"alarm" | "key_9" | "agent"` (04 §4.4 plus `agent`).
- `DEEPINFRA_API_KEY` lives only in `backend/.env` (git-ignored) and Railway variables. Never committed, never logged.
- No migration: every table used already exists.
- Tests never touch the `echocare` database; database tests use the existing fixtures (`db`, `campaign_call`, `live_call`, `add_senior`).

## Review Focus

1. **A new `prompt` arrives while a turn is still streaming, with no `interrupt` first.** The current turn is cancelled and a new turn starts with the new words. Test: Task 5, `test_a_new_prompt_mid_turn_replaces_the_turn`.
2. **The senior hangs up during the tier 2 confirmation.** 03 §4 makes that red: closing the agent while it waits starts the tier 2 hand-over, which does nothing if the call is no longer in progress. Test: Task 5, `test_a_hang_up_during_the_confirmation_hands_over`.
3. **Tool JSON cut off (`finish_reason: "length"`) or malformed.** The `ToolCall` carries `{}`, the rules refuse it with a result the model can act on, and nothing crashes. Tests: Task 2, `test_a_record_with_missing_arguments_is_refused`; Task 3, `test_cut_off_tool_arguments_become_empty`.
4. **No `DEEPINFRA_API_KEY` on a laptop.** Building the model must not raise. The first turn fails into the model-failure path, so the call ends `dropped` instead of hanging. Test: Task 3, `test_building_without_a_key_does_not_raise`.
5. **The hang-up's status callback races the agent's own ending.** Exactly one conclusion and one rules report. Test: Task 4, `test_ending_a_call_already_dropped_does_nothing`.

---

### Task 1: Settings, dependency and contracts

**Files:**
- Modify: `backend/pyproject.toml` (dependency, and `"openai"` in the "status engine is pure" `forbidden_modules`)
- Modify: `backend/app/core/settings.py` (after `twilio_voice`)
- Modify: `backend/.env.example`
- Test: `backend/tests/core/test_settings.py`

**Interfaces:**
- Produces: `Settings.deepinfra_api_key: str = ""`, `Settings.agent_model: str = "deepseek-ai/DeepSeek-V4-Pro"`.

- [ ] **Step 1: Write the failing test** in `tests/core/test_settings.py`

```python
def test_the_agent_model_defaults_to_deepseek_v4_pro(monkeypatch):
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    s = Settings(database_url="postgresql+asyncpg://x/y", _env_file=None)
    assert s.agent_model == "deepseek-ai/DeepSeek-V4-Pro"
    assert s.deepinfra_api_key == ""
```

- [ ] **Step 2: Run it to make sure it fails.** `uv run pytest tests/core/test_settings.py::test_the_agent_model_defaults_to_deepseek_v4_pro -v` should FAIL with an `AttributeError` on `agent_model`.
- [ ] **Step 3: Add the two settings.** Comment: model provider for the agent loop (04 §5, channel 8); the key is a secret (06 §4). In `.env.example`, add a commented block `# DEEPINFRA_API_KEY=` and `# AGENT_MODEL=deepseek-ai/DeepSeek-V4-Pro`.
- [ ] **Step 4: Add the dependency.** Run `uv add openai`. Add `"openai"` to the `forbidden_modules` of the "The status engine is pure logic" contract in `pyproject.toml`; `tests/architecture/test_contracts.py` fails without it.
- [ ] **Step 5: Run the checks.** Run `uv run pytest tests/core/test_settings.py tests/architecture -q && uv run lint-imports`. Expected: all pass.
- [ ] **Step 6: Commit.** `git add pyproject.toml uv.lock app/core/settings.py .env.example tests/core/test_settings.py && git commit -m "agent: DeepInfra settings and the openai dependency (#49, 04 §5)"`

---

### Task 2: Tool rules and instructions

Pure logic, with no I/O. Tested without a database.

**Files:**
- Create: `backend/app/agent/tools.py`
- Create: `backend/app/agent/prompt.py`
- Test: `backend/tests/agent/test_tools.py`

**Interfaces:**
- Consumes: `app.status.engine.{Answer, CallAnswers, Question, Severity}`; `app.agent.relay.Escalation`, extended here with members `tier_2`, `concern`, `rules`, `human` (values `"tier_2"`, `"concern"`, `"rules"`, `"human"`); and `handoff_reason(e: Escalation) -> str` added in `relay.py`. `alarm` and `tier_2` map to `"alarm"`, `key_9` to `"key_9"`, the rest to `"agent"`. `Relay.escalate` switches to `handoff_reason(escalation)`.
- Produces:
  - `TOOLS: list[dict]`: OpenAI function schemas for `record_answer(field: enum feeling|orientation|shelter, value: str, clear: bool, words: str)`, `raise_concern(level: enum yellow|red, reason: str, words: str)`, `request_human(reason: str)` and `end_call(summary: str)`, all fields required. Descriptions as in 04 §5. `request_human`'s description includes "or the conversation cannot go on". `end_call.summary` says "one sentence, in Romanian".
  - `REASKS = 2`
  - `@dataclass Outcome`: `result: str` (what the model is told, English); `hand_over: Escalation | None = None`; `reason: str = ""`; `answer: tuple[Question, Answer] | None = None` (to store); `concern: tuple[Severity, str] | None = None` (to store); `end: str | None = None` (an accepted summary).
  - `class CallRules(today: date)`: attributes `answers: CallAnswers` and `time_up: bool = False`; methods `run(name: str, args: dict) -> Outcome`, `pending() -> Question | None` (an unclear answer that still has a re-ask), `missing() -> list[Question]`, `may_close() -> bool`.
  - `instructions(form_of_address: str, heat: bool) -> str` in `prompt.py`.

**Rules `run` applies (design §5):**
- **`record_answer`**
  - Refused if `field` isn't a `Question`, `clear` isn't a bool, or `value` is outside `{ok, unwell}` for feeling or `{yes, no}` for shelter. Orientation takes any non-empty string. The refusal names the bad argument.
  - `CallAnswers.record` returning False means refused: "a clear answer is already recorded".
  - Otherwise `answer` is set. An unclear record increments a per-question counter; while that count ≤ `REASKS`, the result names the question to ask again, once, slowly.
  - If `answers.severity(today)` is now red: `hand_over=Escalation.rules`.
  - Otherwise the result lists the missing questions, or says all are answered: "say a short goodbye and call end_call".
- **`raise_concern`**
  - Bad level: refused.
  - Otherwise `concern=(Severity[level], reason)`; red sets `hand_over=Escalation.concern` with `reason`.
- **`request_human`:** `hand_over=Escalation.human`, `reason=args.get("reason", "")`.
- **`end_call`**
  - Accepted (`end=summary`) when `time_up`.
  - Otherwise refused while `missing()` is non-empty (naming the questions) or `pending()` is set (naming the question to ask again). Accepted after that.
- **Unknown tool:** refused.
- **`pending()`:** an answer that is unclear with a count ≤ `REASKS`.
- **`may_close()`:** `not missing() and pending() is None`.

- [ ] **Step 1: Write the failing tests** in `tests/agent/test_tools.py`. Build a `CallRules(date(2026, 11, 8))` (a Sunday) in each test, and use `rec(field, value, clear)` as a helper that calls `run("record_answer", {...,"words": "x"})`.

```python
def test_a_clear_answer_is_never_overwritten():
    r = rules(); rec(r, "feeling", "unwell", True)
    out = rec(r, "feeling", "ok", True)
    assert out.answer is None and "already recorded" in out.result
    assert r.answers.answers[Question.feeling].value == "unwell"

def test_an_unclear_answer_is_asked_again_twice_then_kept():
    r = rules()
    for _ in range(2):
        assert "feeling" in rec(r, "feeling", "ok", False).result
        assert r.pending() is Question.feeling
    third = rec(r, "feeling", "ok", False)
    assert r.pending() is None and "again" not in third.result

def test_end_call_waits_for_all_three_and_the_re_asks():
    r = rules()
    assert r.run("end_call", {"summary": "s"}).end is None   # missing all
    rec(r, "feeling", "ok", False); rec(r, "orientation", "duminică", True); rec(r, "shelter", "yes", True)
    refused = r.run("end_call", {"summary": "s"})
    assert refused.end is None and "feeling" in refused.result
    rec(r, "feeling", "ok", True)
    assert r.may_close() and r.run("end_call", {"summary": "s"}).end == "s"

def test_end_call_is_accepted_at_the_time_limit():
    r = rules(); r.time_up = True
    assert r.run("end_call", {"summary": "s"}).end == "s"

def test_unwell_and_a_wrong_day_hands_over_at_once():
    r = rules(); rec(r, "feeling", "unwell", True)
    assert rec(r, "orientation", "marți", True).hand_over is Escalation.rules

def test_a_red_concern_hands_over_and_a_yellow_one_is_only_stored():
    r = rules()
    y = r.run("raise_concern", {"level": "yellow", "reason": "pastile", "words": "w"})
    assert (y.concern, y.hand_over) == ((Severity.yellow, "pastile"), None)
    red = r.run("raise_concern", {"level": "red", "reason": "r", "words": "w"})
    assert red.hand_over is Escalation.concern and red.reason == "r"

def test_request_human_hands_over():
    out = rules().run("request_human", {"reason": "nu aude"})
    assert (out.hand_over, out.reason) == (Escalation.human, "nu aude")

def test_a_record_with_missing_arguments_is_refused():
    out = rules().run("record_answer", {})
    assert out.answer is None and out.result.startswith("refused")

@pytest.mark.parametrize("field,value", [("feeling", "fine"), ("shelter", "maybe"), ("mood", "ok")])
def test_values_outside_the_spec_are_refused(field, value):
    assert rec(rules(), field, value, True).answer is None

def test_an_unknown_tool_is_refused():
    assert rules().run("send_sms", {}).result.startswith("refused")

def test_handoff_reasons():
    assert [handoff_reason(e) for e in Escalation] == ["alarm", "key_9", "alarm", "agent", "agent", "agent"]

def test_the_instructions_name_the_warning_and_the_new_limits():
    cold, heat = instructions("doamna Elena", False), instructions("doamna Elena", True)
    assert "doamna Elena" in cold and "warm place" in cold and "cool place" in heat
    assert "never say you have notified" in cold.lower() and "never give yourself a name" in cold.lower()
```

- [ ] **Step 2: Run the tests to make sure they fail.** `uv run pytest tests/agent/test_tools.py -q` should FAIL on import (`app.agent.tools` missing).
- [ ] **Step 3: Implement `tools.py`, `prompt.py`, and the `Escalation` and `handoff_reason` changes in `relay.py`.** The instructions follow design §4 "Fixed instructions" point by point, in English. They contain the literal phrases "never say you have notified", "never give yourself a name", "warm place" (cold) or "cool place" (heat), and the clear/unclear examples „mda, merge” and „bine, mulțumesc”. Keep the `Escalation` member order: alarm, key_9, tier_2, concern, rules, human.
- [ ] **Step 4: Run the tests.** Run `uv run pytest tests/agent -q && uv run lint-imports`. Expected: all pass, including the existing `test_relay.py`.
- [ ] **Step 5: Commit.** `git commit -m "agent: tool rules and instructions (#49, 04 §5, 03 §3)"` with the four files.

---

### Task 3: DeepInfra model stream

**Files:**
- Create: `backend/app/agent/model.py`
- Test: `backend/tests/agent/test_model.py`

**Interfaces:**
- Consumes: `TOOLS` (Task 2).
- Produces:
  - `@dataclass(frozen=True) ToolCall`: `id: str`, `name: str`, `arguments: dict[str, Any]`.
  - `ModelStream = Callable[[list[dict[str, Any]]], AsyncIterator[str | ToolCall]]`. It yields text pieces as they stream, then the round's complete tool calls, in index order, after the stream ends.
  - `deepinfra(api_key: str, model: str, *, client: Any = None) -> ModelStream`. It creates `openai.AsyncOpenAI(base_url=..., api_key=api_key)` lazily on the first call when `client` is None.

- [ ] **Step 1: Write the failing tests.** A fake client exposes `chat.completions.create(**kwargs)`, records its kwargs, and returns an async iterator of `SimpleNamespace` chunks shaped like OpenAI's: `choices[0].delta.content`, `choices[0].delta.tool_calls[i].{index,id,function.name,function.arguments}`, `choices[0].finish_reason`.

```python
async def test_text_streams_in_order_and_the_request_is_exact():
    client = FakeClient([text_chunk("Bună "), text_chunk("ziua")])
    items = [i async for i in deepinfra("k", "m", client=client)([{"role": "user", "content": "x"}])]
    assert items == ["Bună ", "ziua"]
    kw = client.kwargs
    assert (kw["model"], kw["stream"], kw["temperature"], kw["max_tokens"]) == ("m", True, 0.3, 1000)
    assert kw["extra_body"] == {"reasoning_effort": "none"} and kw["tools"] is TOOLS

async def test_tool_call_pieces_are_joined_after_the_text():
    client = FakeClient([
        tool_chunk(0, id="c1", name="record_answer", args='{"field": "fee'),
        text_chunk("Mulțumesc."),
        tool_chunk(0, args='ling", "value": "ok", "clear": true, "words": "bine"}'),
        tool_chunk(1, id="c2", name="end_call", args='{"summary": "s"}'),
    ])
    items = [i async for i in deepinfra("k", "m", client=client)([])]
    assert items[0] == "Mulțumesc."
    assert items[1:] == [
        ToolCall("c1", "record_answer", {"field": "feeling", "value": "ok", "clear": True, "words": "bine"}),
        ToolCall("c2", "end_call", {"summary": "s"}),
    ]

async def test_cut_off_tool_arguments_become_empty():
    client = FakeClient([tool_chunk(0, id="c1", name="record_answer", args='{"field": "feeling"', finish="length")])
    assert [i async for i in deepinfra("k", "m", client=client)([])] == [ToolCall("c1", "record_answer", {})]

def test_building_without_a_key_does_not_raise():
    deepinfra("", "deepseek-ai/DeepSeek-V4-Pro")
```

- [ ] **Step 2: Run the tests to make sure they fail.** `uv run pytest tests/agent/test_model.py -q` should FAIL on import.
- [ ] **Step 3: Implement `model.py`.** Gather tool-call deltas per `index` as in the bake-off script. Log a warning (not the content) on `finish_reason == "length"`. `json.loads` failure, or a non-dict result, becomes `{}`. A missing id becomes `f"call_{index}"`.
- [ ] **Step 4: Run the tests.** Run `uv run pytest tests/agent/test_model.py -q && uv run lint-imports`. Expected: pass.
- [ ] **Step 5: Commit.** `git commit -m "agent: DeepInfra model stream (#49, 04 §5)"`

---

### Task 4: Ending: stored answers, concerns, dropped calls, hand-over severity

**Files:**
- Modify: `backend/app/voice/service.py` (add `save_answer` beside `save_turn`)
- Modify: `backend/app/calls/ending.py` (`conclude`, `settle`, `begin_handover`; new `call_reason`, `stored_answers`, `stored_concern`, `save_concern`, `end_wellbeing`)
- Modify: `backend/app/calls/service.py` (`AnswerContext` gains `heat: bool = False`, set from `Campaign.kind is CampaignKind.heat`)
- Test: `backend/tests/calls/test_ending.py`

**Interfaces:**
- Produces:
  - `voice.service.save_answer(call_id: UUID, field: Question, value: str, *, clear: bool, quote: str) -> None`. Owns its session and commits, like `save_turn`; it wraps `record_answer` with `at=datetime.now(UTC)`.
  - `ending.save_concern(call_id: UUID, severity: Severity, reason: str) -> None`. Owns its session; writes `add_report(..., ReportSource.raise_concern, severity, reason[:200])` and commits.
  - `ending.stored_answers(session, call_id) -> CallAnswers`. Reads `answers` by `at` and applies them through `CallAnswers.record`, so the overwrite rule holds.
  - `ending.stored_concern(session, call_id) -> Severity | None`. The highest severity among the call's `raise_concern` reports.
  - `ending.call_reason(session, call, answers) -> str`. The campaign kind lookup and `campaign_reason`, moved out of `conclude`. With no worrying answer and a question missing, it returns `INCOMPLETE_REASON = "Nu a răspuns la toate întrebările"`.
  - `conclude(session, call, answers, *, summary: str = "Apel simulat din aplicație.", concern: Severity | None = None, dropped: bool = False) -> Severity | None`. The stored summary becomes `f"{summary} {reason}."`. `dropped=True` means certainty is `Certainty.low`, the end state is `CallState.dropped`, and there's no redial. `concern` passes to `final_severity(concern=...)`. The mock card's call site is unchanged.
  - `settle`: a non-test, non-welcome call that moves to `dropped` now runs `conclude(session, call, await stored_answers(...), concern=await stored_concern(...), dropped=True)`.
  - `end_wellbeing(call_id: UUID, summary: str, *, dropped: bool = False) -> Severity | None`. Owns its session. It locks the live call (`live_call_for_update`), concludes from the stored answers and concern, and commits. Returns None, writing nothing, when the call is no longer in progress.
  - `begin_handover(call_id, source, reason: str | None) -> bool`. Severity is red for `RED_SOURCES = {alarm_tier1, alarm_tier2, raise_concern, rules}`, otherwise yellow. `reason=None` means `call_reason(session, call, stored_answers(...))`.

- [ ] **Step 1: Write the failing tests** in `tests/calls/test_ending.py`. Use `live_call` and `campaign_call`; `save_answer` and `save_concern` write through their own sessions, then `db` reads.

```python
async def test_stored_answers_keep_a_clear_answer(db, live_call):
    call = await live_call()
    await save_answer(call.id, Question.feeling, "unwell", clear=True, quote="mi-e rău")
    await save_answer(call.id, Question.feeling, "ok", clear=True, quote="acum bine")
    assert (await stored_answers(db, call.id)).answers[Question.feeling].value == "unwell"

async def test_a_hang_up_after_mi_e_rau_ends_yellow_without_a_redial(db, live_call):
    call = await live_call(code=Severity.green)
    await save_answer(call.id, Question.feeling, "unwell", clear=True, quote="mi-e rău")
    await settle(db, call.id, None, CallState.dropped)
    ended = await db.get(Call, call.id); await db.refresh(ended)
    assert (ended.state, ended.final_severity, ended.final_certainty) == ("dropped", "yellow", "low")
    assert await db.scalar(select(func.count()).select_from(Call)) == 1   # no redial

async def test_a_hang_up_after_the_greeting_ends_yellow_incomplete(db, live_call):
    call = await live_call(code=Severity.green)
    await settle(db, call.id, None, CallState.dropped)
    ended = await db.get(Call, call.id); await db.refresh(ended)
    assert (ended.final_severity, ended.reason) == ("yellow", "Nu a răspuns la toate întrebările")

async def test_a_stored_concern_raises_the_result(db, live_call):
    call = await live_call(code=Severity.green)
    for q, v in [(Question.feeling, "ok"), (Question.orientation, today_name()), (Question.shelter, "yes")]:
        await save_answer(call.id, q, v, clear=True, quote=v)
    await save_concern(call.id, Severity.yellow, "Nu-și găsește pastilele de inimă")
    assert await end_wellbeing(call.id, "Rezumat.") is Severity.yellow

async def test_ending_a_clear_green_call_completes_with_the_summary(db, live_call):
    call = await live_call(code=Severity.green)
    for q, v in [(Question.feeling, "ok"), (Question.orientation, today_name()), (Question.shelter, "yes")]:
        await save_answer(call.id, q, v, clear=True, quote=v)
    assert await end_wellbeing(call.id, "Doamna se simte bine.") is Severity.green
    ended = await db.get(Call, call.id); await db.refresh(ended)
    assert ended.state == "completed" and ended.summary.startswith("Doamna se simte bine.")

async def test_a_model_failure_ends_dropped(db, live_call):
    call = await live_call(code=Severity.green)
    assert await end_wellbeing(call.id, "Convorbirea s-a întrerupt.", dropped=True) is Severity.yellow
    assert (await db.get(Call, call.id)).state == "dropped"

async def test_ending_a_call_already_dropped_does_nothing(db, live_call):
    call = await live_call()
    await settle(db, call.id, None, CallState.dropped)
    assert await end_wellbeing(call.id, "x") is None
    reports = await db.scalar(select(func.count()).select_from(StatusReport).where(StatusReport.call_id == call.id))
    assert reports == 1

async def test_a_red_from_the_rules_hands_over_with_the_answers_reason(db, live_call):
    call = await live_call(code=Severity.green)
    await save_answer(call.id, Question.feeling, "unwell", clear=True, quote="rău")
    await save_answer(call.id, Question.shelter, "no", clear=True, quote="nu")
    assert await begin_handover(call.id, ReportSource.rules, None)
    status = await code_of(db, call)
    assert status.code is Severity.red and "se simte rău" in status.reason.lower()

async def test_a_red_concern_hands_over_red(db, live_call):
    call = await live_call(code=Severity.green)
    assert await begin_handover(call.id, ReportSource.raise_concern, "Durere de cap puternică")
    assert (await code_of(db, call)).code is Severity.red
```

`today_name()` returns the Romanian weekday for `today_in_bucharest()` from `WEEKDAYS`. `code_of` already exists in this file.

- [ ] **Step 2: Run the tests to make sure they fail.** `uv run pytest tests/calls/test_ending.py -q` should FAIL on import (`save_answer` and the others are missing).
- [ ] **Step 3: Implement the functions above.** `conclude`'s answered branch takes `certainty = Certainty.low if dropped else answers.certainty()` and `end = CallState.dropped if dropped else CallState.completed`. `finish` already treats the same state as a no-op, so the `settle` path, where `transition` has already moved the call to dropped, works unchanged.
- [ ] **Step 4: Run the whole backend suite.** Run `uv run pytest -q && uv run lint-imports`. Expected: all pass. The mock-call and existing ending tests are unchanged.
- [ ] **Step 5: Commit.** `git commit -m "calls: conclude dropped calls from stored answers and concerns (#49, 03 §6, 03 §9)"`

---

### Task 5: The agent state machine

**Files:**
- Create: `backend/app/agent/loop.py`
- Test: `backend/tests/agent/test_loop.py`

**Interfaces:**
- Consumes: `CallRules`, `Outcome`, `TOOLS` and `instructions` (Task 2); `ModelStream` and `ToolCall` (Task 3); `Escalation`, `handoff_reason`, `HandOver`, `Store`, `CONNECTING` from `relay.py`; `app.status.alarms.{check, Tier, confirmation_question, needs_help, SELF_HARM_HANDOVER}`.
- Produces:
  - `Send = Callable[[dict[str, Any]], Awaitable[None]]`.
  - `@dataclass(frozen=True) Line`: `store: Store`; `answer: Callable[[Question, Answer], Awaitable[None]]`; `concern: Callable[[Severity, str], Awaitable[None]]`; `hand_over: HandOver`, called with `(Escalation, reason)` and returning True when it started; `end: Callable[[str, bool], Awaitable[None]]`, called with `(summary, dropped)`.
  - `@dataclass(frozen=True) Limits`: `first_token: float = 10.0`, `call_limit: float = 180.0`, `tier2_wait: float = 8.0`, `rounds: int = 3`.
  - `class Agent(*, call: str, greeting: str, form_of_address: str, heat: bool, send: Send, line: Line, model: ModelStream, today: date | None = None, limits: Limits = Limits())` with:
    - `async handle(message: dict) -> None`: returns quickly; a turn runs as a task.
    - `async close() -> None`: cancels the turn and timers; a pending confirmation hands over (Review Focus 2).
    - `async idle() -> None`: awaits the running turn, for tests.
    - `finished: bool`: True once `end` was sent; nothing is sent after it.
  - Romanian copy, module constants: `FAILURE = "Ne pare rău, avem o problemă tehnică și trebuie să închidem. La revedere."`, `STALL = "Vă mulțumesc."`, `TIME_UP = "Vă mulțumesc pentru timpul acordat. La revedere."`, `DEFAULT_SUMMARY = "Convorbire cu asistentul."`, `DROPPED_SUMMARY = "Convorbirea s-a întrerupt."`, `TIME_UP_SUMMARY = "Limita de timp a apelului."`.

**Behaviour (design §4, §5):**
- **`setup`:** store the greeting as an agent turn. The history becomes `[system: instructions(...), assistant: greeting]`. Start the call-limit timer.
- **`prompt` with `last` False:** store it, no reply.
- **`prompt` with `last` True:**
  - Store it.
  - While a confirmation is pending, it is the reply: `needs_help(words)` True means hand over `tier_2`; False means a system turn „Confirmare nivel 2: nu” (plan's call: kept in the transcript for review, instead of a report). Then append the matched sentence and the reply as user messages and start a turn.
  - Otherwise `check(words)`. Tier 1 hands over `alarm`, speaking `SELF_HARM_HANDOVER` for `self_harm`, otherwise `CONNECTING`. Tier 2 sends `confirmation_question(words)` as one `text` with `last: True`, stores it, and starts the 8 s timer; on expiry it hands over `tier_2`.
  - Otherwise cancel any running turn, append the user message and start a turn.
- **`dtmf`:** store it. During a confirmation, `1` means hand over `tier_2` and `2` counts as the "no" path. `9` hands over `key_9`. Other keys: nothing.
- **`interrupt`:**
  - Cancel the turn.
  - Roll the history back to its length when the turn started, then append `{"role": "assistant", "content": utteranceUntilInterrupt}`.
  - Store the system turn `interrupted after: …`, the existing wording.
- **`error`:** log it and store a system turn, as today.
- **A turn:**
  - Up to `limits.rounds` model calls.
  - **Text:** each piece is sent as `{"type": "text", "token": piece, "last": False}`, holding back the latest piece so the round's final piece goes out with `last: True`.
  - **JSON guard:** if the round's first non-whitespace character is `{`, none of the round's text is sent; log it and treat the round as having no text.
  - **History:** append the assistant message (`content` text or None, plus `tool_calls` in OpenAI format).
  - **Tools:** run each tool call through `CallRules.run`. Store `outcome.answer` through `line.answer` and `outcome.concern` through `line.concern`, then append a `tool` message with `outcome.result`.
  - **Transcript:** store the spoken text as an agent turn.
  - **Stop conditions:** if any outcome has `hand_over`, hand over (`line.hand_over(e, reason)`; on True send `CONNECTING`, store it, then `{"type": "end", "handoffData": json.dumps({"call": call, "reason": handoff_reason(e)})}`) and stop. Stop if the round had text or no tool calls.
  - **Third round without text:** send and store `STALL`.
  - **After the rounds:** if a summary was accepted, or `rules.may_close()`, call `await line.end(summary or DEFAULT_SUMMARY, False)`, then send `{"type": "end"}`.
- **Model failure:** an exception from the stream, or no first item within `limits.first_token`. Send and store `FAILURE`, call `line.end(DROPPED_SUMMARY, True)`, and send `end`.
- **Call limit:**
  - Cancel the turn and set `rules.time_up = True`.
  - Send and store `TIME_UP`.
  - Call `line.end(TIME_UP_SUMMARY, False)` and send `end`.

- [ ] **Step 1: Write the failing tests** with three fakes:
  - `FakeModel(rounds: list[list[str | ToolCall | Exception]])`: each call pops one round, yields its items (raising an `Exception` item), and records a copy of the messages it was given.
  - `FakeLine`: records `turns`, `answers`, `concerns`, `hand_overs` and `ends`; `hand_over` returns True.
  - `sent`: a list fed by `send`.

  Build with `Limits(first_token=0.2, call_limit=5, tier2_wait=0.05)`, send `SETUP` first, and `await agent.idle()` before asserting. Name `R = ToolCall("c1", "record_answer", {...})` per case.

```python
async def test_the_04_5_conversation_reaches_a_close():
    model = FakeModel([
        [rec("feeling", "ok", False)], ["Vă simțiți ", "bine acum?"],
        [rec("feeling", "ok", True), rec("orientation", SUNDAY, True), "Aveți căldură?"],
        [rec("shelter", "yes", True), "La revedere."],
    ])
    a, line, sent = make(model, today=date(2026, 11, 8))
    for words in ["mda, merge", "bine, e duminică", "da"]:
        await a.handle(prompt(words)); await a.idle()
    assert {"type": "text", "token": "bine acum?", "last": True} in sent
    assert sent[-1] == {"type": "end"} and line.ends == [("Convorbire cu asistentul.", False)]
    assert "feeling" in model.calls[1][-1]["content"]          # the re-ask named in the tool result

async def test_a_text_round_ends_the_turn():
    model = FakeModel([["Bine.", rec("feeling", "ok", True)]])
    a, _, _ = make(model); await a.handle(prompt("bine")); await a.idle()
    assert len(model.calls) == 1

async def test_three_tool_only_rounds_say_the_stall_line():
    model = FakeModel([[rec("feeling", "ok", True)]] * 3)
    a, _, sent = make(model); await a.handle(prompt("bine")); await a.idle()
    assert texts(sent) == [STALL] and len(model.calls) == 3

async def test_json_looking_text_is_never_sent():
    model = FakeModel([['{"name": "record_answer"', '}'], ["Ce zi e azi?"]])
    a, _, sent = make(model); await a.handle(prompt("bine")); await a.idle()
    assert texts(sent) == ["Ce zi e azi?"]

async def test_a_red_from_the_rules_hands_over_with_reason_agent():
    model = FakeModel([[rec("feeling", "unwell", True), rec("shelter", "no", True)]])
    a, line, sent = make(model); await a.handle(prompt("rău, n-am căldură")); await a.idle()
    assert line.hand_overs == [(Escalation.rules, "")]
    assert json.loads(sent[-1]["handoffData"])["reason"] == "agent"

async def test_request_human_hands_over(): ...          # ToolCall request_human -> (Escalation.human, reason), reason "agent"
async def test_a_red_concern_hands_over_and_a_yellow_is_stored(): ...
async def test_tier_1_hands_over_without_the_model():   # prompt "am căzut" -> model.calls == [], (Escalation.alarm, "am căzut")
async def test_self_harm_says_its_own_line(): ...       # "vreau să mor" -> texts(sent) == [SELF_HARM_HANDOVER]

@pytest.mark.parametrize("reply", [prompt("da"), dtmf("1"), None])   # None: wait past tier2_wait
async def test_tier_2_yes_or_silence_hands_over(reply): ...          # "am leșinat" first -> (Escalation.tier_2, "am leșinat")

@pytest.mark.parametrize("reply", [prompt("nu"), dtmf("2")])
async def test_tier_2_no_goes_to_the_model(reply): ...    # no hand-over; model.calls[0] has both sentences as user messages

async def test_key_9_hands_over(): ...
async def test_interrupt_cancels_and_keeps_what_was_heard(): ...
    # model round yields "Doamna Elena, " then awaits an Event forever; interrupt(heard="Doamna Elena")
    # -> turn cancelled, line.turns ends with (system, speech, "interrupted after: Doamna Elena"),
    # next model call's messages[-2] == {"role": "assistant", "content": "Doamna Elena"}
async def test_a_new_prompt_mid_turn_replaces_the_turn(): ...         # Review Focus 1
async def test_a_model_error_drops_the_call(): ...      # round [RuntimeError()] -> texts == [FAILURE], ends == [(DROPPED_SUMMARY, True)], sent[-1] == {"type": "end"}
async def test_no_first_token_in_time_drops_the_call(): ...           # model sleeps 1 s, first_token 0.2
async def test_the_time_limit_closes_with_the_answers_so_far(): ...   # call_limit=0.05 -> TIME_UP, ends == [(TIME_UP_SUMMARY, False)]
async def test_may_close_ends_without_end_call(): ...
async def test_nothing_is_sent_after_end(): ...
async def test_a_hang_up_during_the_confirmation_hands_over(): ...    # Review Focus 2: tier 2, then close() -> (Escalation.tier_2, ...)
async def test_close_cancels_a_running_turn_quietly(): ...
```

Write the elided bodies to the one-line assertion in each comment.

- [ ] **Step 2: Run the tests to make sure they fail.** `uv run pytest tests/agent/test_loop.py -q` should FAIL on import.
- [ ] **Step 3: Implement `loop.py`.** Use one `asyncio.Task` for the turn and one each for the call-limit and confirmation timers. Wrap the first item in `asyncio.timeout(limits.first_token)`, for example `anext` on the stream's async iterator. Every send goes through one guard that drops it once `finished` is set.
- [ ] **Step 4: Run the tests.** Run `uv run pytest tests/agent -q && uv run lint-imports`. Expected: all pass.
- [ ] **Step 5: Commit.** `git commit -m "agent: the conversation loop (#49, 04 §4.3, 04 §5, 03 §4)"`

---

### Task 6: Wiring: session, router, echo for test calls

**Files:**
- Modify: `backend/app/agent/session.py` (`serve` takes a handler factory; add `Echo`)
- Modify: `backend/app/voice/router.py` (`relay`, `hand_over_for`, new `model_stream`, `agent_for`, `echo_for`)
- Modify: `backend/tests/voice/test_voice.py` (new `serve` signature; the echo-specific test uses a test call)
- Test: `backend/tests/voice/test_voice.py`

**Interfaces:**
- Consumes: `Agent`, `Line`, `Limits`, `Send` (Task 5); `deepinfra` (Task 3); `save_answer`, `save_concern`, `end_wellbeing`, `begin_handover`, `AnswerContext.heat` (Task 4).
- Produces:
  - `class Handler(Protocol)` in `session.py`: `async handle(message) -> None`, `async close() -> None`.
  - `serve(ws: Socket, call: UUID, start: Callable[[Send], Handler]) -> None`. The setup and one-time checks are unchanged. It builds the handler after `accept`, forwards every message including `setup`, and calls `close()` on disconnect.
  - `class Echo(relay: Relay, send: Send, call: UUID)` in `session.py`. Today's behaviour: send `Relay.handle`'s replies, calling `end_completed` first when an `end` has no `handoffData`.
  - `voice/router.py`:
    - `model_stream() -> ModelStream` returns `deepinfra(s.deepinfra_api_key, s.agent_model)`; tests monkeypatch it.
    - `echo_for(call, greeting)` and `agent_for(call, context)` each return a factory taking `Send`.
    - `relay` uses `echo_for` for `CallTrigger.test`, `agent_for` otherwise.
  - `hand_over_for` maps:

| Escalation | ReportSource | Reason |
|---|---|---|
| `key_9` | `request_human` | `KEY_9_REASON` |
| `alarm` | `alarm_tier1` | `ALARM_REASON.format(words=...)`, truncated as today |
| `tier_2` | `alarm_tier2` | `ALARM_REASON.format(words=...)`, truncated as today |
| `concern` | `raise_concern` | the model's reason[:200] |
| `human` | `request_human` | the model's reason[:200], or `"A cerut un operator"` when empty |
| `rules` | `rules` | `None` |

- [ ] **Step 1: Update the existing tests and write the new ones** in `tests/voice/test_voice.py`.
  - Each direct `agent_session.serve(ws, call.id, "Bună ziua.")` becomes `agent_session.serve(ws, call.id, echo_for(call.id, "Bună ziua."))`.
  - In `test_our_close_ends_completed`, set the fixture call's `trigger` to `"test"` before `answered(...)`, since key 0 is echo-only.
  - Give `Socket` an optional `drain: float = 0` that `receive_text` awaits once before raising `WebSocketDisconnect`, so a turn task can finish.

```python
async def test_a_wellbeing_call_talks_to_the_model(client, db, call, monkeypatch):
    async def stream(messages):
        yield "Mă bucur. Ce zi e azi?"
    monkeypatch.setattr(voice_router, "model_stream", lambda: stream)
    await answered(client, call)
    ws = Socket(call.id, [SETUP, {"type": "prompt", "voicePrompt": "bine", "last": True}], drain=0.2)
    await voice_router.relay(ws, call.id)
    assert {"type": "text", "token": "Mă bucur. Ce zi e azi?", "last": True} in ws.sent

async def test_a_test_call_still_echoes(client, db, call):
    call.trigger = "test"; await db.commit()
    await answered(client, call)
    ws = Socket(call.id, [SETUP, {"type": "prompt", "voicePrompt": "bine", "last": True}])
    await voice_router.relay(ws, call.id)
    assert ws.sent[0]["token"].startswith("Am auzit")

async def test_a_model_hand_over_sends_reason_agent(client, db, call, monkeypatch):
    async def stream(messages):
        yield ToolCall("c1", "request_human", {"reason": "nu aude"})
    monkeypatch.setattr(voice_router, "model_stream", lambda: stream)
    await answered(client, call)
    ws = Socket(call.id, [SETUP, {"type": "prompt", "voicePrompt": "alo?", "last": True}], drain=0.2)
    await voice_router.relay(ws, call.id)
    assert json.loads(ws.sent[-1]["handoffData"])["reason"] == "agent"
    assert (await stored(db, call)).state == "handed_over"
```

`test_key_9_on_a_wellbeing_call_ends_handed_over` must still pass unchanged through the agent.

- [ ] **Step 2: Run the tests to make sure the new ones fail.** `uv run pytest tests/voice/test_voice.py -q`. Expected: the new tests FAIL (`echo_for` and `model_stream` missing).
- [ ] **Step 3: Implement the session and router changes.** `agent_for` builds `Line` with:
  - `store=partial(save_turn, call)`
  - `answer=lambda q, a: save_answer(call, q, a.value, clear=a.clear, quote=a.words)`
  - `concern=partial(save_concern, call)`
  - `hand_over=hand_over_for(call)`
  - `end=lambda summary, dropped: end_wellbeing(call, summary, dropped=dropped)`

  The `Agent` gets `call=str(call)` (it goes into `handoffData`) and `model=model_stream()`; its `greeting`, `form_of_address` and `heat` come from `context`. The `end` callable returns None; `end_wellbeing`'s result is ignored.
- [ ] **Step 4: Run the full checks.** Run `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`. Expected: all pass.
- [ ] **Step 5: Commit.** `git commit -m "voice: wellbeing calls talk to the agent, test calls keep the echo (#49, 04 §4.3)"`

---

### Task 7: Spec updates and the local smoke check

Contract changes move with the code (AGENTS.md). From the repository root.

**Files:**
- Modify: `docs/specs/echocare/04-interfaces.md`:
  - §4.3: replace "Built so far (#48)" with the loop's behaviour.
  - §4.4 step 2: reason `"alarm" | "key_9" | "agent"`.
  - §5: provider chosen; `request_human` meaning; the two new limits; up to 2 re-asks.
- Modify: `docs/specs/echocare/03-status-model.md`:
  - §5: "Retry once" for an answered call becomes up to two re-asks; the redial stays one.
  - §6: an MVP note that yellow takes effect at the call's end and red at once.
- Modify: `docs/specs/echocare/01-architecture.md` §8: drop "(proposed)" from the agent-loop sentence.
- Modify: `docs/specs/echocare/06-operations.md` §6: an S4 row dated 2026-11-08. Text bake-off: DeepSeek-V4-Pro chosen, 8/8 hard scenarios, 2.0 s median and 4.1 s p90 to the first word from Timișoara; Gemma 4 31B turbo the faster alternative; phone confirmation still to do.
- Modify: `docs/specs/echocare/README.md`: strike open question 4, as questions 3 and 13 are struck, with "Resolved by S4 (2026-11-08): DeepInfra, DeepSeek-V4-Pro."

- [ ] **Step 1: Make the edits above.** Keep each table's existing style. Cite #49.
- [ ] **Step 2: Check that nothing else still says the provider is unchosen.** Run `grep -rn "not chosen\|Built so far (#48)" docs/specs/echocare/`. Expected: no output.
- [ ] **Step 3: Run a local smoke check with a key** (manual, not CI). With `DEEPINFRA_API_KEY` in `backend/.env`, run `docker compose up --watch db` and `cd backend && uv run pytest -q`. Then use the mock-free path, a campaign call to a team number on `DIAL_ALLOWLIST` through the ngrok profile, as in 06 §6 S1. Record in 06 §6 S4 how the voice sounded and the wait before the first word. If no phone test is possible now, write "phone confirmation still to do" and leave it.
- [ ] **Step 4: Commit.** `git add docs/specs/echocare && git commit -m "spec: agent loop, provider chosen, two re-asks, hand-over reason agent (#49, S4)"`
