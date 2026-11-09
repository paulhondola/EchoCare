# Senior Summary Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One living summary per senior, written after every answered wellbeing call by a Pydantic AI agent, read by the next call (one follow-up), by the DAS dashboard (briefing and trend notes), and the live call loop moved onto Pydantic AI's model layer.

**Architecture:** A new `app/memory/` package holds the summary agent, its citation validator and the scheduler step that starts it outside the locked tick. Versions are rows in a new `senior_summaries` table owned by `seniors`, whose `schemas.py` also holds the summary's Pydantic shape, shared by the agent's `output_type`, the API and the live call. The live call gets only the first follow-up question and the how-to-talk notes through `AnswerContext`, and the rules engine sees none of it. Phase 4 swaps what sits behind `agent/model.py`'s `ModelStream` seam for `pydantic_ai.direct.model_request_stream`, and the history in `loop.py` becomes Pydantic AI messages. The turn control stays in `loop.py`.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async, Alembic, `pydantic-ai-slim[openai]`, `pydantic-evals` (dev), DeepInfra's OpenAI-compatible API, pytest (asyncio auto). Dashboard: Svelte 5, SvelteKit 3, TypeScript, Vite+.

**Spec:** [docs/superpowers/specs/2026-11-08-senior-summary-agents-design.md](../specs/2026-11-08-senior-summary-agents-design.md) ("design" below). Read all of it before any task, along with the spec sections it cites (03 §3, §6, §11; 04 §1, §4.3, §5; 05 §4, §5; 06 §2, §4; 01 §8).

## Global Constraints

- Branch `63-senior-summary-agents`. Backend commands run from `backend/`, dashboard commands from `dashboard/`. Commit with the lefthook hooks on, never `--no-verify`. Each phase leaves the branch green and demoable, so a PR can be cut after any phase.
- After every backend task: `uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`. After every dashboard task: `npm run check && npx svelte-check --tsgo --fail-on-warnings && npx vp test`.
- Pydantic AI is a fast-moving library. Before Task 1, read the installed version's docs for `Agent(output_type=…, deps_type=…, output_retries=…)`, `@agent.output_validator`, `ModelRetry`, `TestModel`, `FunctionModel`, `OpenAIChatModel`, `OpenAIProvider` and `pydantic_ai.direct.model_request_stream`. If a name differs from this plan, use the installed one. If `model_request_stream` can't meet an acceptance check in Task 11, stop and report back, and **never** fall back to `Agent.iter()` (design §8).
- Safety lines, verbatim from the design:
  1. The summary never feeds the status engine. Red and yellow come only from the rules, alarm phrases, `raise_concern`, `request_human` and key 9.
  2. In a call, the summary can only add one follow-up question. It never replaces, skips or answers one of the three questions.
  3. Every summary version is kept, with the call it came from.
- Who reads it: the senior's registering medic and DAS for a senior past `draft`, the same reach as the transcript. Anyone else gets `404 not_found`.
- No senior words in logs: log the call id, lengths and error types only. No `logfire`, no `instrument=True`, no `Agent.instrument_all()`.
- `SUMMARY_MODEL` defaults to `deepseek-ai/DeepSeek-V4-Pro`. Live model settings stay exactly `temperature=0.3`, `max_tokens=1000`, `extra_body={"reasoning_effort": "none"}`, base URL `https://api.deepinfra.com/v1/openai`.
- Summary bounds: at most 3 `follow_ups`, 3 `how_to_talk` notes of ≤120 chars, 3 `trends` each with ≥2 evidence from different calls, and a `narrative` of ≤600 chars. Quotes are ≤200 chars. The validator allows 2 retries, and the scheduler 3 attempts per call per process.
- Timing: summarize calls that ended within the last 24 h. A `handed_over` call waits until its newest turn is over 2 minutes old. The live loop keeps its 10 s per-chunk timeout, 3 rounds per turn and 180 s limit.
- API and migrations only add (ADR-001 §2.3). A contract change updates `04-interfaces.md`, the backend and the dashboard in the same task. Android doesn't call the new read.
- `app.agent` still imports only `app.voice`, `app.status` and external packages. Only `seniors` writes `senior_summaries` (ADR-005).
- User-facing text is Romanian: summary content, dashboard labels, the follow-up. Code, comments and docs are English, and comments cite the spec by ID.
- Database tests use `echocare_test` through the existing fixtures (`db`, `add_senior`, `add_active_senior`, `client`). Unit tests never call DeepInfra.

## Review Focus

1. **Two calls for one senior end before the first summary is written.** The second waits until the first version exists, then builds on it (`previous_id` set, in call order). Test: Task 4, `test_a_seniors_calls_are_summarized_in_order`.
2. **A mock card call: answers, no speech turns.** It qualifies, and a citation quoting an answer's `quote` passes the validator. Test: Task 3, `test_an_answer_quote_is_a_valid_citation`.
3. **The model's quote differs from the transcript only in diacritics, case or punctuation** (ş/ș, ţ/ț, „”). It passes after `app.status.alarms.normalize`. Test: Task 3, `test_a_quote_matches_after_normalization`.
4. **A stored version whose JSON no longer fits `SummaryContent`** (a later field change). The live call goes ahead without notes, and the API serves nothing for it instead of a 500. Tests: Task 5, `test_unreadable_content_gives_no_notes`; Task 7, `test_unreadable_content_is_no_summary`.
5. **Consent is withdrawn between the hang-up and the summary step.** The call is not summarized. Test: Task 4, `test_a_withdrawn_senior_is_not_summarized`.

---

## Phase 1: the summary agent and the next call's memory (A)

### Task 1: Dependencies, settings, the shared DeepInfra model, contracts

**Files:**
- Modify: `backend/pyproject.toml`: add `pydantic-ai-slim[openai]` to runtime and `pydantic-evals` to dev, through `uv add`. Add `"pydantic_ai"` to the status engine's `forbidden_modules`. Add `memory` to the layers contract as `"calls | agent | system | memory"`.
- Modify: `backend/app/core/settings.py` (`summary_model: str = "deepseek-ai/DeepSeek-V4-Pro"`), `backend/.env.example` (`SUMMARY_MODEL=`)
- Create: `backend/app/core/llm.py`, `backend/app/memory/__init__.py` (empty)
- Test: `backend/tests/core/test_llm.py`, `backend/tests/architecture/test_contracts.py`

**Interfaces:**
- Produces: `app.core.llm.BASE_URL = "https://api.deepinfra.com/v1/openai"`; `deepinfra_model(api_key: str, name: str) -> OpenAIChatModel`, which never raises without a key and makes no network call while building. `Settings.summary_model`.

- [ ] **Step 1:** Write `test_building_without_a_key_does_not_raise`: `deepinfra_model("", "x")` returns a model whose `model_name == "x"`.
- [ ] **Step 2:** Write `test_no_instrumentation` in `tests/architecture/test_contracts.py`. It scans every `.py` under `app/` and asserts that none contains `logfire`, `instrument=True` or `instrument_all`.
- [ ] **Step 3:** Run both and check that `test_building_without_a_key_does_not_raise` fails (`ModuleNotFoundError: app.core.llm`).
- [ ] **Step 4:** Run `uv add 'pydantic-ai-slim[openai]'` and `uv add --dev pydantic-evals`, update the contracts in `pyproject.toml`, and add the setting. Implement `deepinfra_model` with `OpenAIChatModel(name, provider=OpenAIProvider(base_url=BASE_URL, api_key=api_key or "missing"))`. The placeholder key exists because the OpenAI client refuses an empty one at construction. A call made with it fails, and the loop's failure path handles that.
- [ ] **Step 5:** Run the full backend check line. `test_status_forbids_every_dependency` must pass.
- [ ] **Step 6:** Commit with `git commit -m "memory: pydantic-ai, SUMMARY_MODEL, shared DeepInfra model (#63, design §3, §7)"`.

### Task 2: The `senior_summaries` table, its shape, the owner's write and read

**Files:**
- Modify: `backend/app/seniors/models.py` (ORM `SummaryVersion`), `backend/app/seniors/schemas.py` (the content shape and the view), `backend/app/seniors/service.py`, `backend/app/models/__init__.py` (export `SummaryVersion`)
- Create: `backend/alembic/versions/<rev>_senior_summaries.py`, generated in Compose: `docker compose exec api alembic revision --autogenerate -m "senior summaries"`. Review it: one `create_table` and its indexes, nothing else.
- Modify (spec): `docs/specs/echocare/05-data-model.md` §1 (entity `SENIOR_SUMMARY` in the ER diagram), §2 (the columns), §5 (retention row: the transcript's)
- Test: `backend/tests/seniors/test_summaries.py`

**Interfaces:**
- Produces, in `app.seniors.models`: `SummaryVersion`, table `senior_summaries`. Columns: `id` uuid pk; `senior_id` FK `seniors.id`, indexed; `call_id` FK `calls.id`, **unique**; `previous_id` FK `senior_summaries.id`, nullable; `content` JSONB; `model` String(120); `created_at` from `timestamp_now()`.
- Produces, in `app.seniors.schemas`, Romanian text inside and English field names:
  - `Citation(BaseModel)`: `call_id: uuid.UUID`, `quote: str` (max 200)
  - `FollowUp(BaseModel)`: `topic: str` (max 120), `question: str` (max 200), `call_id: uuid.UUID`, `quote: str` (max 200)
  - `Trend(BaseModel)`: `note: str` (max 200), `direction: Literal["worse", "better", "steady"]`, `evidence: list[Citation]` (min 2)
  - `SummaryContent(BaseModel)`: `follow_ups: list[FollowUp]` (max 3), `how_to_talk: list[Annotated[str, max 120]]` (max 3), `trends: list[Trend]` (max 3), `narrative: str` (max 600)
  - `SummaryVersionView(BaseModel)`: `content: SummaryContent`, `call_id: uuid.UUID`, `created_at: datetime`
- Produces, in `app.seniors.service`:
  - `add_summary(session, *, senior_id, call_id, previous_id: uuid.UUID | None, content: SummaryContent, model: str) -> None`. Doesn't commit, and stores `content.model_dump(mode="json")`.
  - `latest_summary(session, senior_id) -> SummaryVersion | None`, newest `created_at`, ties broken by `id`.
  - `read_content(version: SummaryVersion) -> SummaryContent | None`, which returns None when the stored JSON no longer validates, and logs the version id.

- [ ] **Step 1:** Write the tests:
  - `test_a_version_is_kept_per_call`: two `add_summary` calls with the same `call_id`, then a flush, raise `IntegrityError`.
  - `test_latest_is_the_newest`: the second of two versions is returned, and its `previous_id` is the first's id.
  - `test_bounds_hold`: `SummaryContent` with 4 follow-ups, or a trend with one evidence, or a narrative of 601 chars, raises `ValidationError`.
  - `test_read_content_of_old_json_is_none`: `read_content` of a version whose content is `{"narrative": 5}` returns None.
- [ ] **Step 2:** Run `uv run pytest tests/seniors/test_summaries.py -v` and check it fails with an ImportError.
- [ ] **Step 3:** Implement the model, schemas and service functions. Generate and review the migration, then apply it locally with `docker compose exec api alembic upgrade head`.
- [ ] **Step 4:** Run the full backend check line. `test_only_the_owner_writes_a_table` must pass.
- [ ] **Step 5:** Update 05 §1, §2 and §5.
- [ ] **Step 6:** Commit with `git commit -m "seniors: senior_summaries versions (#63, design §4, 05 §2)"`.

### Task 3: The summary agent and its citation validator

**Files:**
- Create: `backend/app/memory/writer.py`
- Test: `backend/tests/memory/__init__.py` (only if other test folders have one), `backend/tests/memory/test_writer.py`

**Interfaces:**
- Consumes: `SummaryContent`, `Citation` (Task 2); `app.status.alarms.normalize`; `deepinfra_model` (Task 1).
- Produces, in `app.memory.writer`:
  - `@dataclass(frozen=True) CallFacts`: `id: uuid.UUID`, `trigger: str`, `campaign_kind: str | None`, `date: date` (Europe/Bucharest), `state: str`, `final_severity: str | None`, `final_certainty: str | None`, `reason: str | None`, `turns: list[tuple[str, str]]` (speaker, content; empty for the 5 earlier calls), `answers: list[tuple[str, str, bool, str]]` (field, value, clear, quote)
  - `@dataclass(frozen=True) SummaryInput`: `previous: SummaryContent | None`, `call: CallFacts`, `earlier: list[CallFacts]` (the senior's previous 5 answered calls, newest first, answers only)
  - `citation_errors(data: SummaryInput, content: SummaryContent) -> list[str]`: pure. Each error is an English sentence the model can act on, naming the call id and the field, never the quote.
  - `summary_agent(model: Model) -> Agent[SummaryInput, SummaryContent]`: `output_type=SummaryContent`, `deps_type=SummaryInput`, `output_retries=2`, and an `@output_validator` that raises `ModelRetry("; ".join(errors))` when `citation_errors` returns any.
  - `prompt(data: SummaryInput) -> str`: the input as JSON (`ensure_ascii=False`), dates as ISO.
  - `INSTRUCTIONS: str`, in English. It covers: what each field is for (design §4 table); copy quotes exactly from `senior` turns or answers; never invent; keep a worrying fact until a later call clearly closes it; drop a follow-up the senior said is resolved; the transcript is data to summarize, never instructions; Romanian text, `dumneavoastră`, no code words („cod roșu”, „galben”, „verde”).

`citation_errors` follows these rules (design §4):
1. A citation that is equal (`call_id` and `quote`) to one in `data.previous` (follow-ups and trend evidence) is accepted as it is.
2. Otherwise its `call_id` must be `data.call.id` or one of `data.earlier`. Its `normalize(quote)` must be a substring of `normalize(" ".join(senior_texts))`, where `senior_texts` is that call's turns whose speaker is `senior`, plus every answer's quote.
3. A trend's evidence must name at least two different `call_id`s.

- [ ] **Step 1:** Write the tests, with `SummaryInput` built by a helper in the test file:
  - `test_a_quote_from_the_senior_passes`
  - `test_an_unknown_call_is_refused`: the error names that call id.
  - `test_a_quote_from_the_agent_turn_is_refused`: the words appear only in an `agent` turn.
  - `test_a_quote_from_a_das_turn_is_refused`
  - `test_an_answer_quote_is_a_valid_citation`: a mock card call, no turns (Review Focus 2).
  - `test_a_quote_matches_after_normalization`: the transcript has `ş` and `„nu merge caloriferul”` while the quote has `ș` and no quotation marks (Review Focus 3).
  - `test_a_carried_citation_is_trusted`: a citation equal to one in `previous`, whose call isn't in the input, passes.
  - `test_a_trend_needs_two_calls`: two evidence items from one call are refused.
  - `test_the_agent_retries_then_fails`: `summary_agent(FunctionModel(...))` returns a bad citation on every attempt, `agent.run(prompt(d), deps=d)` raises `UnexpectedModelBehavior`, and the function was called 3 times.
  - `test_the_agent_returns_a_valid_summary`: with `TestModel(custom_output_args=<valid content dict>)`, `run` returns that `SummaryContent`.
- [ ] **Step 2:** Run `uv run pytest tests/memory/test_writer.py -v` and check it fails with an ImportError.
- [ ] **Step 3:** Implement `writer.py`.
- [ ] **Step 4:** Run the full backend check line.
- [ ] **Step 5:** Commit with `git commit -m "memory: summary agent and citation validator (#63, design §4)"`.

### Task 4: Which calls are summarized, and the scheduler step

**Files:**
- Create: `backend/app/memory/service.py`
- Modify: `backend/app/scheduler/loop.py` (a fifth step `("summarized", start_summaries)`, after `silenced`; its signature already fits, so it needs no wrapper)
- Modify (spec): `docs/specs/echocare/06-operations.md` §2 (the step), `04-interfaces.md` §5 (a new subsection "The summary agent": input, output, when it runs, who reads it)
- Test: `backend/tests/memory/test_service.py`, `backend/tests/scheduler/test_loop.py` (`patch_steps` gains `start_summaries`)

**Interfaces:**
- Consumes: Task 2's `add_summary`, `latest_summary`, `read_content`; Task 3's `SummaryInput`, `CallFacts`, `summary_agent`, `prompt`; `deepinfra_model`; `get_settings().summary_model`.
- Produces, in `app.memory.service`:
  - `WELLBEING = {CallTrigger.campaign, CallTrigger.watch, CallTrigger.manual}`, `ANSWERED = {CallState.completed, CallState.handed_over, CallState.dropped}`, `WINDOW = timedelta(hours=24)`, `TALK_QUIET = timedelta(minutes=2)`, `ATTEMPTS = 3`
  - `due_calls(session, now) -> list[uuid.UUID]`: at most one call per senior, the oldest that qualifies (design §4 "Which calls" and "When it runs"). It skips calls with `ATTEMPTS` failures in this process and seniors with a running task.
  - `summary_input(session, call_id) -> tuple[uuid.UUID, uuid.UUID | None, SummaryInput]`: returns (senior id, previous version id, input).
  - `write_summary(call_id, *, model: Model | None = None) -> None`: owns its session. It reads the input, runs the agent, then calls `add_summary` and commits. An `IntegrityError` on the unique `call_id` is a no-op: another copy wrote it first.
  - `start_summaries(now: datetime) -> int`: opens a session, calls `due_calls`, and starts one `asyncio.Task` per call running `write_summary`. Returns how many it started. **It never awaits a task.** State is module-level: `_running: dict[uuid.UUID, asyncio.Task]` keyed by senior, and `_failures: Counter[uuid.UUID]` keyed by call. A task's done-callback removes it from `_running`. When the task failed, the callback adds to `_failures` and logs `"summary failed, call %s: %s"` with the call id and `type(e).__name__`.
A call qualifies when all of these hold: `trigger ∈ WELLBEING`; `state ∈ ANSWERED`; the senior is `active`; `ended_at >= now - WINDOW`; there's no `SummaryVersion` with its `call_id`; `ended_at` is later than the `ended_at` of the call behind the senior's latest version; and, for `handed_over`, `max(call_turns.at) < now - TALK_QUIET`.

- [ ] **Step 1:** Write the tests, building calls with the fixtures plus `Call` and `CallTurn` rows, and patching `app.memory.service.summary_agent` so that it returns an agent on `TestModel`:
  - `test_a_completed_campaign_call_is_due`
  - `test_skipped_calls`: parametrized over a test call, a welcome call, an `unanswered` call, a `failed` call, a call ended 25 h ago, and a call older than the latest version's. None of them is due.
  - `test_a_handed_over_call_waits_for_the_das_talk`: a turn 1 minute old makes it not due, and the same turn 3 minutes old makes it due.
  - `test_a_withdrawn_senior_is_not_summarized` (Review Focus 5)
  - `test_a_seniors_calls_are_summarized_in_order`: two calls end, so the first step starts only the older one. After its task finishes, the next step starts the newer one, whose `previous_id` is the first version (Review Focus 1).
  - `test_a_failing_call_is_tried_three_times`: the agent raises every time. After 3 failed tasks, `due_calls` no longer returns that call.
  - `test_a_second_copy_writing_the_same_call_is_a_no_op`: `write_summary` twice for one call leaves one row and raises nothing.
  - `test_logs_name_no_words`: a failing task's log record contains the call id and the error type, and none of the turn's content.
  - In `tests/scheduler/test_loop.py`, `test_the_tick_never_waits_for_a_summary`: `write_summary` is patched to await an `asyncio.Event` that is never set. `tick(NOW)` returns `True`, and the advisory lock is free afterwards.
- [ ] **Step 2:** Run the tests and check that they fail.
- [ ] **Step 3:** Implement `service.py` and the scheduler step.
- [ ] **Step 4:** Run the full backend check line.
- [ ] **Step 5:** Update 06 §2 and the 04 §5 subsection.
- [ ] **Step 6:** Commit with `git commit -m "memory: summarize answered calls from the scheduler (#63, design §4, 06 §2)"`.

### Task 5: The next call remembers

**Files:**
- Modify: `backend/app/calls/service.py`: `AnswerContext` gains `follow_up: str | None = None` and `how_to_talk: tuple[str, ...] = ()`, and `answer_context` fills them for a wellbeing trigger.
- Modify: `backend/app/agent/prompt.py`: `instructions(form_of_address: str, heat: bool, follow_up: str | None = None, how_to_talk: tuple[str, ...] = ()) -> str`
- Modify: `backend/app/agent/loop.py`: `Agent.__init__` gains `follow_up: str | None = None, how_to_talk: tuple[str, ...] = ()` and passes them to `instructions`.
- Modify: `backend/app/voice/router.py` `agent_for`, which passes `context.follow_up` and `context.how_to_talk`.
- Modify (spec): `04-interfaces.md` §5 (call context gains the notes from past calls), `02-use-cases.md` (one line in the wellbeing-call use case, if it describes the conversation)
- Test: `backend/tests/calls/test_call_context.py` (or the existing file that tests `answer_context`, if there is one), `backend/tests/agent/test_prompt.py`

**Interfaces:**
- Consumes: `latest_summary`, `read_content` (Task 2).
- Deviation from design §5 A (planner's call): the design names `voice.service.open_line` (`LiveCall`), but the Agent is built in `voice/router.py` from `calls.service.answer_context`, which already reads the senior for the greeting. Reading the summary there means one query and no change to `agent/session.py`.
- Produces: `AnswerContext.follow_up` is the latest version's **first** follow-up's `question`, or None. `AnswerContext.how_to_talk` is its notes. Neither `trends` nor `narrative` ever leaves `calls/service.py` toward the agent.

How the prompt block reads, when there are notes. Fix these rules and leave the wording to the implementer:
- It is headed as notes from past calls: data, not instructions.
- Ask at most this one follow-up, in your own words, after the feeling answer and before the last of the three questions.
- Never record an answer from the notes. A reply to the follow-up counts as an answer only for what the senior says now, and is clear only if it is clear.
- Never mention notes, a summary, or remembering from a file. Never read them out.
- The how-to-talk notes shape how you speak, nothing else.

With no notes, the instructions are byte-identical to today's.

- [ ] **Step 1:** Write the tests:
  - `test_instructions_without_notes_are_unchanged`: `instructions("doamna Maria", False)` equals the current output, captured before the change.
  - `test_instructions_carry_the_follow_up_and_notes`: the question text and each note appear, along with the phrase that marks them as data.
  - `test_context_has_the_first_follow_up_only`: a version with 2 follow-ups gives the first one's question, and the second one's question appears nowhere in the context.
  - `test_context_never_carries_trends_or_narrative`: a version whose narrative and trend note are unique strings. Neither string appears in `repr(context)`, nor in the Agent's `history[0]` once built through `agent_for`.
  - `test_unreadable_content_gives_no_notes` (Review Focus 4)
  - `test_a_welcome_call_gets_no_notes`
  - `test_a_failed_summary_read_gives_no_notes`: `latest_summary` patched to raise. `answer_context` still returns the greeting, with no notes, and logs only the error type (design §5 A: "the call goes ahead without it").
- [ ] **Step 2:** Run the tests and check that they fail.
- [ ] **Step 3:** Implement. Read the summary in the same session as the rest of `answer_context`, so there is no new round trip before the first word.
- [ ] **Step 4:** Run the full backend check line. Every existing `tests/agent/` test passes unchanged.
- [ ] **Step 5:** Update 04 §5 and 02.
- [ ] **Step 6:** Commit with `git commit -m "agent: one follow-up from the senior's summary (#63, design §5 A)"`.

### Task 6: Evals, run by hand

**Files:**
- Create: `backend/evals/__init__.py`, `backend/evals/summary.py`, `backend/evals/README.md` (one paragraph: what it is, the command, that it costs money)
- Modify (spec): `docs/specs/echocare/06-operations.md` §5 (testing rows for the summary agent and its evals), §4 (the privacy lines of design §7), `01-architecture.md` (module table: `memory` and the scheduler's new step; §3's model provider row names DeepInfra), `03-status-model.md` (§3 or §6: one sentence saying the summary never feeds severity or certainty; §11 as in design §5 C), `docs/specs/echocare/README.md` (decision-log entry; open question: a consent version that covers remembering across calls)

**Interfaces:**
- Consumes: `SummaryInput`, `CallFacts`, `summary_agent`, `prompt`, `citation_errors`.
- Produces: `uv run python -m evals.summary` runs a `pydantic_evals.Dataset` of about 10 cases against `SUMMARY_MODEL` on DeepInfra and prints the report.

The cases are at least the 7 in design §9. Evaluators:
- deterministic: `citation_errors` returns nothing, the bounds hold, no `cod roșu`/`galben`/`verde` in `follow_ups`, and each case's expected topic is present or absent
- one `LLMJudge` for "faithful and natural Romanian"

The pass bar and the judge model are the implementer's call. Ruff covers `evals/`, and CI doesn't run it.

- [ ] **Step 1:** Write the dataset and the evaluators.
- [ ] **Step 2:** Run `uv run python -m evals.summary` with a real `DEEPINFRA_API_KEY` in `backend/.env`. Record the scores for the PR description.
- [ ] **Step 3:** Update the spec files listed above.
- [ ] **Step 4:** Commit with `git commit -m "memory: summary evals and spec (#63, design §9, §10)"`.

---

## Phase 2: the DAS briefing (B)

### Task 7: `GET /seniors/{id}/summary` and `summary` on the incident

**Files:**
- Modify: `backend/app/seniors/service.py` (`summary_for`), `backend/app/seniors/router.py` (the route), `backend/app/incidents/schemas.py` (`IncidentDetail.summary: SummaryVersionView | None = None`), `backend/app/incidents/service.py` (`load_incident` fills it)
- Modify (spec): `docs/specs/echocare/04-interfaces.md` §1 (the new read and the optional incident field)
- Modify: `dashboard/src/services/api.ts`. Add the types `SummaryContent`, `SummaryVersion`, `IncidentDetail.summary?: SummaryVersion | null` and `fetchSummary(seniorId, signal): Promise<SummaryVersion | null>`, which returns null on 204.
- Test: `backend/tests/seniors/test_summaries.py`, `backend/tests/incidents/test_incident_view.py`

**Interfaces:**
- Consumes: `latest_summary`, `read_content`, `SummaryVersionView`; `reach(caller, Role.medic)` and `reach(caller, Role.das)`, as in `calls/service.py` `transcript`.
- Produces: `summary_for(session, caller, senior_id) -> SummaryVersionView | None`, which raises `refuse(404, "not_found")` when the senior is outside medic-or-DAS reach. The route `GET /seniors/{senior_id}/summary` returns the view, or `Response(status_code=204)` when there is none. Declare `responses={204: …}`, as `/profile/mock-call` does.

- [ ] **Step 1:** Write the tests, through `client`:
  - `test_summary_reach`, parametrized: the registering medic gets 200, DAS gets 200, a caregiver of the senior gets 404 `not_found`, the senior herself gets 404, and a stranger medic gets 404. DAS on a `draft` senior gets 404.
  - `test_no_summary_is_204`
  - `test_unreadable_content_is_no_summary`: 204 (Review Focus 4).
  - `test_incident_carries_the_summary`: `GET /incidents/{id}` has `summary.content.narrative` equal to the latest version's.
  - `test_incident_without_summary_has_null`
- [ ] **Step 2:** Run the tests and check that they fail.
- [ ] **Step 3:** Implement the backend changes, then the `api.ts` types and fetch.
- [ ] **Step 4:** Run the backend check line and the dashboard check line.
- [ ] **Step 5:** Update 04 §1.
- [ ] **Step 6:** Commit with `git commit -m "seniors: the summary read and the incident briefing field (#63, design §5 B, 04 §1)"`.

### Task 8: The briefing and trend notes on the dashboard

This task also covers Phase 3's display ("Observații"), since the same component shows it.

**Files:**
- Create: `dashboard/src/features/seniors/Briefing.svelte` (props: `summary: SummaryVersion | null`, `calls?: { id: string; started_at: string | null }[]` to date citations), `dashboard/src/utils/briefing.ts`, `dashboard/src/utils/briefing.test.ts`
- Modify: `dashboard/src/features/seniors/SeniorDetails.svelte` (fetches with `fetchSummary` next to `fetchCalls`, and shows `Briefing`), `dashboard/src/features/incidents/IncidentDetails.svelte` (shows `Briefing` from `incident.summary` in the "Urgență & acces" tab, under the access block; the implementer may place it elsewhere)
- Modify: `dashboard/AGENTS.md` layout lines for the new files

**Interfaces:**
- Produces, in `utils/briefing.ts`:
  - `DIRECTION: Record<"worse" | "better" | "steady", string>` = `{ worse: "În înrăutățire", better: "În îmbunătățire", steady: "Stabil" }`
  - `citedOn(callId: string, calls: {id: string; started_at: string | null}[]): string`, the call's date in the existing `labels.ts` date format, or `"apel anterior"` when the call isn't in the list.

Sections, with these Romanian labels: „Pe scurt” (the narrative), „Subiecte deschise” (each follow-up's topic and quote), „Cum vorbim cu dumneaei/dumnealui” (choose the gender-neutral wording „Cum vorbim” if unsure), and „Observații” (each trend: note, direction label, and evidence quotes with their dates). Add the footer line „Rezumat după apelul din {date}”. With no summary, show „Niciun rezumat încă.” Colours come from the neutral tokens (`fg-muted`, `line`, `card`), **never** `rosu`, `galben` or `verde`. `calls` is the `CallSummary` list `SeniorDetails` already fetches; the incident passes its own `calls`. The design's optional senior-list marker for a `worse` trend is left out (planner's call: not needed for the demo).

- [ ] **Step 1:** Write `briefing.test.ts`: the `DIRECTION` labels; `citedOn` for a known call and an unknown one.
- [ ] **Step 2:** Run `npx vp test` and check that it fails.
- [ ] **Step 3:** Implement `briefing.ts`, `Briefing.svelte` and the two placements.
- [ ] **Step 4:** Run the dashboard check line. Then run `docker compose up --watch` and seed (Task 9 if done, otherwise one version inserted through Task 2's test helper). Open http://localhost:5173 and check the senior slide-over and an incident dossier, in the browser pane, with a screenshot.
- [ ] **Step 5:** Commit with `git commit -m "dashboard: senior briefing and Observații (#63, design §5 B, C)"`.

---

## Phase 3: seeded history (C)

### Task 9: A demo senior with a slow decline and their versions

**Files:**
- Modify: `backend/scripts/seed.py` (`build` adds one demo senior; `History` gains `summaries: list[SummaryVersion]`; `save` adds them after `history.rows`, in order; `remove` deletes seeded `senior_summaries` before calls)
- Test: `backend/tests/tooling/test_scripts.py`

**Interfaces:**
- Consumes: `SummaryVersion`, `SummaryContent` (Task 2); `CallFacts`, `SummaryInput`, `citation_errors` (Task 3).

Content (design §6): one `active` senior, ids from `seed_id(...)`, with 6 answered campaign calls spread over 3 weeks. The wrong day comes up in 2 of the last 3 calls, along with „nu prea mai ies din casă”, and the latest call mentions „nu merge caloriferul”. Each call has a fixed-text version, chained by `previous_id`. The latest has the heater as follow-up 1 and one `worse` trend citing the two wrong-day calls. The seed makes no model call. Leave `seed_cast.py` alone.

- [ ] **Step 1:** Write the tests:
  - `test_seed_writes_a_chain_of_versions`: after `seed(reset=True)`, the demo senior has 6 versions, each `previous_id` is the one before, and each `call_id` is distinct.
  - `test_seeded_citations_are_real`: for each version, `citation_errors` against an input built from its own call and the earlier ones (turns included) is empty. This guards the fixed text against edits that drift from the transcripts.
  - `test_seed_reset_is_repeatable`: two `seed(reset=True)` runs give the same version count.
- [ ] **Step 2:** Run the tests and check that they fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the full backend check line. Run `uv run python scripts/seed.py --reset` locally and check that the dashboard shows the Observații.
- [ ] **Step 5:** Commit with `git commit -m "seed: demo senior with a decline and summary versions (#63, design §6)"`.

---

## Phase 4: the live loop on Pydantic AI

### Task 10: The model seam on `model_request_stream`

**Files:**
- Modify: `backend/app/agent/model.py`, `backend/app/agent/tools.py` (tool schemas from Pydantic models)
- Modify: `backend/app/voice/router.py` `model_stream()`, which builds `stream_with(deepinfra_model(key, agent_model))`
- Test: `backend/tests/agent/test_model.py`, `backend/tests/agent/test_tools.py`

**Interfaces:**
- Consumes: `deepinfra_model` (Task 1).
- Produces, in `app.agent.tools`: the Pydantic models `RecordAnswerArgs`, `RaiseConcernArgs`, `RequestHumanArgs` and `EndCallArgs`, each with `model_config = ConfigDict(extra="forbid")` and today's field descriptions. `TOOL_DEFS: list[ToolDefinition]` (name, description, `parameters_json_schema=Args.model_json_schema()`) replaces `TOOLS`. `CallRules.run` is unchanged and still takes `dict[str, Any]`.
- Produces, in `app.agent.model`: `ModelStream = Callable[[list[ModelMessage]], AsyncIterator[str | ToolCall]]`. `SETTINGS = ModelSettings(temperature=0.3, max_tokens=1000, extra_body={"reasoning_effort": "none"})`. `stream_with(model: Model) -> ModelStream`. `ToolCall` is unchanged.

`stream_with` works like this. It runs `async with model_request_stream(model, messages, model_settings=SETTINGS, model_request_parameters=ModelRequestParameters(function_tools=TOOL_DEFS)) as s:`. For every event it yields the text: a `PartStartEvent` with a `TextPart` yields its content, a `PartDeltaEvent` with a `TextPartDelta` yields its `content_delta`, and any other event yields `""` (liveness, design §4). After the stream, it yields a `ToolCall(p.tool_call_id, p.tool_name, p.args_as_dict())` for each `ToolCallPart` of `s.get()`. A `{}` replaces arguments that fail to parse. It logs a warning when the finish reason is length. Leaving the generator early exits the `async with`, which closes the HTTP stream.

- [ ] **Step 1:** Write the tests, each on `FunctionModel(stream_function=…)`:
  - `test_settings_reach_the_model`: the stream function's `AgentInfo.model_settings` equals `SETTINGS`, and `[t.name for t in info.function_tools] == ["record_answer", "raise_concern", "request_human", "end_call"]` (acceptance check 11).
  - `test_text_streams_as_pieces`
  - `test_tool_call_pieces_yield_liveness`: a tool-call-only stream yields `""` items before its `ToolCall`.
  - `test_bad_tool_arguments_become_empty`
  - `test_closing_early_closes_the_stream`: the stream function's `finally` runs when the consumer calls `aclose()` after the first piece (acceptance check 9).
  - In `test_tools.py`, `test_tool_schemas_forbid_extra_fields`: each schema has `additionalProperties: false` and lists all its fields as required.
- [ ] **Step 2:** Run the tests and check that they fail.
- [ ] **Step 3:** Implement. Keep `deepinfra()`'s old name only if something still imports it. Otherwise remove it and the `openai` import.
- [ ] **Step 4:** Run `uv run pytest tests/agent/test_model.py tests/agent/test_tools.py -v` and check that both pass. The loop tests can't run yet, since Task 11 converts the history.
- [ ] **Step 5:** Commit together with Task 11, since the loop and the seam change type together. Don't commit a red tree.

### Task 11: The history as Pydantic AI messages, every PR #62 guarantee kept

**Files:**
- Modify: `backend/app/agent/loop.py` (`self.history: list[ModelMessage]`, `_assistant`, `_start_turn`, `_run_turn`, `_heard`)
- Modify: `backend/tests/agent/test_agent_loop.py` (`FakeModel` takes `list[ModelMessage]`; the helpers `users()` and `texts()` read Pydantic AI parts)
- Modify (spec): `01-architecture.md` §8 ("Pydantic AI at the model layer; the turn control stays ours"), `04-interfaces.md` §5 (Pydantic AI in place of the `openai` package and "no agent framework")
- Modify: `backend/pyproject.toml`: remove `openai` from the runtime dependencies if nothing imports it. Keep it in `forbidden_modules`, which may list more than the dependencies.

**Interfaces:**
- Consumes: `ModelStream`, `stream_with`, `TOOL_DEFS` (Task 10); `follow_up` and `how_to_talk` (Task 5).

How the messages map:
- The instructions become `ModelRequest([SystemPromptPart(instructions(...))])`.
- The greeting becomes `ModelResponse([TextPart(greeting)])`.
- Each senior utterance becomes `ModelRequest([UserPromptPart(w)])`.
- A round becomes one `ModelResponse` with a `TextPart` (if there is text) and a `ToolCallPart` per call, followed by one `ModelRequest` of `ToolReturnPart(tool_name, content=o.result, tool_call_id=c.id)`.
- `_spoken` indexes the `ModelResponse` whose `TextPart` an interrupt edits. Edit it with `dataclasses.replace` on the part, or rebuild the response; never mutate a frozen part. An empty heard text with no tool calls removes that response.

- [ ] **Step 1:** Map each acceptance check (design §8, 1–11) to a test in `tests/agent/`. Where an existing test proves it, keep it and convert it to the new message types. Where none exists, add one with this name:
  1. `test_an_interrupt_trims_history_to_what_was_heard`
  2. `test_a_cancel_never_leaves_a_tool_call_without_its_result`
  3. `test_writes_finish_after_an_interrupt`
  4. `test_a_quiet_stream_drops_the_call` (tool-call pieces count as liveness)
  5. `test_the_last_piece_goes_out_with_last_true`
  6. `test_a_red_hand_over_survives_a_cancel`
  7. `test_three_tool_only_rounds_say_the_stall_line` (exists)
  8. `test_json_looking_text_is_never_sent` (exists)
  9. Task 10's `test_closing_early_closes_the_stream`, plus `test_an_interrupt_closes_the_model_stream`: a fake stream's `finally` runs at the interrupt.
  10. `test_logs_carry_no_words`: caplog over a whole scripted call. No senior or model text appears in any record.
  11. Task 10's `test_settings_reach_the_model`.
- [ ] **Step 2:** Run `uv run pytest tests/agent -v` and check that it fails on the type change.
- [ ] **Step 3:** Implement the conversion in `loop.py`. Turn control, round counting, shields, claims and timeouts stay as they are.
- [ ] **Step 4:** Run the full backend check line. All tests pass, the converted PR #62 tests included.
- [ ] **Step 5:** Update 01 §8 and 04 §5.
- [ ] **Step 6:** Commit with `git commit -m "agent: the live loop on Pydantic AI's model layer (#63, design §8, 01 §8)"`.

### Task 12: Phone check on staging (manual, by a team member)

This task needs a deploy to staging, which the plan does not do on its own (AGENTS.md: leave cloud environments alone). The person who runs it confirms the deploy first.

- [ ] **Step 1:** After merge to `main` and the staging deploy, run design §6's demo script on the team member's allow-listed number:
  1. A cold campaign call where they say „nu merge caloriferul, dar mă simt bine”. It ends with the rules' code.
  2. Within a minute, the dashboard senior page shows a new version with the heater.
  3. End the campaign, start a new one, and the second call asks about the heater before the last question.
  4. In one call, interrupt mid-reply. In another, say a tier 1 phrase, which hands over.
- [ ] **Step 2:** Read the first-word wait from the logs of three calls. The median must be no worse than S4's 2.0 s within noise (06 §6). Record the results in the PR.
