# Agent loop design (#49)

Date: 2026-11-08. Issue: [#49](https://github.com/paulhondola/EchoCare/issues/49), branch `49-agent-loop`.
Spec: 04 §4.3 and §5, 03 §3–§5 and §9, 01 §8, 06 §3 and §6 (S2, S4).

## 1. Intent

Today `agent/relay.py` repeats what it hears. On a wellbeing call it should hold a real Romanian conversation, cover the three questions (feeling, orientation, shelter) and record the answers through tools. The server keeps the last word on the code. The model reports what it heard; the rules in `status/engine.py` decide severity, certainty and action, as 03 §3 says.

Done when (from #49): on staging, a team member answers a campaign call, talks with the agent in Romanian, and the call ends with the code the rules give for their answers. Saying a tier 1 phrase hands the call to the on-duty phone.

This is an MVP. The design covers the paths in the spec and the decisions below. Rare edge cases get the simplest safe behaviour, not their own machinery.

## 2. Goals, non-goals, anti-goals

**Goals**
- A natural, short Romanian conversation that reaches all three answers in about 1–2 minutes.
- A short wait before the agent's first word. The bake-off measured about 2 s median for the chosen model, on top of Twilio's 2 s `speechTimeout`.
- Every server rule of 04 §5 ("What the server enforces regardless of the model") holds even when the model misbehaves.
- The call ends through `calls.ending`, the same path the mock card uses, so codes, incidents and redials behave the same.

**Non-goals**
- The room reading in the call context (P22, proposed). Asking where the senior is. (Both out of scope in #49.)
- An agent framework, or a second provider in code. The model is one setting; nothing else switches.
- Spike S2 (collecting alarm-phrase transcripts) is still a #49 task, but it is data collection, not part of this design.
- Rate limits or caps on model-started hand-overs.

**Anti-goals: a failure even if it technically works**
- The agent reads tool-call JSON aloud, makes up a name for itself, or claims it has notified someone. All three happened with some models in the bake-off.
- A clear worrying answer ends up overwritten, or a call ends green because the model judged a vague answer clear.
- Long silences: a senior who hears nothing says „alo?” and hangs up.
- Medical advice beyond water, warmth or shade, and rest.

## 3. Decisions made in the design session

| Decision | Choice | Whose |
|---|---|---|
| Framework | None. Plain provider SDK, as 01 §8 proposed. ConversationRelay already turns speech into text and back, so Pipecat adds nothing | User |
| Provider | DeepInfra (the team holds credits). OpenAI-compatible API: the `openai` Python package with `base_url="https://api.deepinfra.com/v1/openai"` | User |
| Model | `deepseek-ai/DeepSeek-V4-Pro`, kept as a setting. `google/gemma-4-31B-it-turbo` is the faster alternative (about 1.2 s median, also passed every scenario) | User, after the bake-off below; Gemma was my recommendation |
| Who may escalate | The model may hand a call to a person on its own judgment, not only when the senior asks. "She can't hear me / we can't communicate" is a real reason to hand over | User |
| Re-asks per unclear question | **2** (spec said 1) | User |
| Other escalation knobs | Unchanged from the spec: tier 2 confirmation wait 8 s, silence or an unclear reply counts as red; call length limit 3 min; 1 redial after 20 min; on-duty ring 30 s, then a call-back; `speechTimeout` 2 s; an uncertain green that survives its re-asks becomes yellow | User ("proceed") |

### Bake-off evidence (S4, text only, 2026-11-08)

A throwaway script played the 04 §5 conversation and eight hard scenarios against DeepInfra models. The senior was scripted and the tools ran on the real `status/engine.py` rules. Each scenario ran once per model, so the timings are noisy.

| Model | Hard scenarios passed | First word median / p90 | Note |
|---|---|---|---|
| DeepSeek-V4-Pro | 8/8 | 2.0 s / 4.1 s | Good Romanian. Asks for clarification before recording a vague answer |
| Gemma 4 31B turbo | 8/8 | 1.2 s / 2.8 s | Occasional made-up word |
| Qwen3.8-Max | 8/8 | 3.7 s / 4.5 s | Flat |
| Claude Opus 5.5 | 8/8 | 4.5 s / 10.6 s | Best Romanian. Claimed „am anunțat deja un coleg” |
| Claude Sonnet 5.5 | 8/8 | 3.0 s / 5.6 s | Made up a name: „sunt Maria de la DAS” |
| Claude Haiku 4.5 | outcomes ok | 0.7 s / 2.2 s | Broken Romanian, mixed with English („newell”) |
| Kimi-K2.6 | 7/8 | 1.6 s / 2.7 s | Missed the heart-pills concern: the call ended green |
| Qwen3-235B-2507, GLM-5.2 | out | | Tool calls came back as text, so they would be spoken aloud |
| DeepSeek-V4-Flash | out | | Recorded a shelter answer the senior never gave |

Scenarios: hidden dizziness, a confused day, missing heart pills, a broken heater, a senior who wants a person, a suspicious senior asking about medication, a senior who retracts „mi-e rău”, and a hard-of-hearing senior who rambles. None of their lines matches an alarm phrase, so on a real call every one reaches the model. The script lives outside the repository and is not part of the build.

Lessons that shape the design:
- The bigger models changed no outcome code. The split between model and server works.
- Claude through DeepInfra sometimes reasons despite `reasoning_effort: "none"`. With `max_tokens=300` that cut tool-call JSON off (`finish_reason: "length"`). Hence the token cap in §4.
- Several models spoke in the same reply as a tool call, before seeing the tool's result, so they did not know which question was still missing. Hence the round rule in §4.

## 4. The turn loop

One `prompt` from Twilio (with `last` not false) that passes the alarm-phrase check (§5) starts one **turn**:

1. Send the model: the fixed instructions, the call context, the whole conversation so far, and the tools. Parameters: `stream=True`, `temperature=0.3`, `max_tokens=1000`, `extra_body={"reasoning_effort": "none"}`.
2. Stream the reply. Each text piece goes to Twilio at once as a `text` message; the last piece has `last: true`. Tool calls are gathered from the stream.
3. Run the gathered tool calls through the server rules (§5) and add the results to the conversation.
4. **Round rule:**
   - If a tool result started a hand-over, stop and hand over.
   - If the round produced text, the turn is over. Its tool results are already in the conversation for the next turn.
   - If it produced only tool calls, call the model again.
   - At most **3 rounds** per turn. If round 3 still has no text, say a fixed short sentence that keeps the line alive (a builder's choice).
5. If the rules now allow the call to close (§5), the server ends the call once this turn's text has been sent, whether or not the model called `end_call`.

**Model failure:** a provider error, or no first token within **10 s** of the request. The agent says one fixed sentence (for example „Ne pare rău, avem o problemă tehnică. Vă căutăm din nou.”) and the call ends `dropped`. A dropped call is concluded like any other: see "Dropped calls" in §5. Alarm phrases and key 9 never depend on the model.

**Interrupt:** on `interrupt`, stop sending the current reply (cancel the streaming request) and store how much the senior heard, from `utteranceUntilInterrupt`, in the conversation and in the transcript. The next `prompt` starts a fresh turn.

**Concurrency:** the session must keep reading Twilio messages while a turn streams, so an `interrupt`, key 9 or a hang-up acts at once. A turn therefore runs as its own task that the receive loop can cancel. The current `Relay.handle()` returns its messages synchronously, so it has to change shape. That is the main structural change in `agent/`.

**Unsafe text guard:** if a text piece starts like JSON (`{"name"` or `{"`), don't send it to Twilio; log it and count the round as producing no text. This is cheap protection against the Qwen and GLM failure if the model is ever switched.

### Fixed instructions

Written in English with Romanian voice rules, the way the bake-off prompt was. It worked. Content, from 04 §5 plus the session's lessons:

- Who it is: the phone assistant of DAS Timișoara, calling during a heat or cold warning. Its words are spoken by a voice: no lists, no emoji, no markdown.
- Tone: warm, slow, simple Romanian; at most two short sentences per reply; "dumneavoastră" and the senior's form of address.
- The three questions, one at a time, with what to record (03 §3). Never say whether the named day is right.
- When an answer counts as clear, with examples. „mda, merge” and „așa și așa” are not clear; „bine, mulțumesc” is.
- `raise_concern` for something serious outside the three questions. `request_human` when the senior asks for a person **or when the conversation can't go on** (she can't hear, can't follow, or is distressed).
- After all three, a short goodbye and `end_call`.
- Limits from 04 §5: no medical advice beyond water, shade or warmth, and rest; no promises; never ask for money, codes or personal data; ask for confirmation when an answer is ambiguous. **New, from the bake-off:** never say it has notified or called anyone; never give itself a name.

### Call context

The senior's form of address, the trigger and why the call is happening, and for a campaign the warning kind and level (heat or cold). The wording can come from `voice.dialogue` the way the greeting does. The greeting itself is the conversation's first agent turn: Twilio speaks it from the TwiML, and `setup` already stores it.

## 5. Server rules, with this session's changes

As in 04 §5 and 03 §3–§4 unless marked **changed**.

| Rule | Behaviour |
|---|---|
| Alarm phrases | `status.alarms.check` on every `prompt` before the model sees it. Tier 1: red and a hand-over, as built in #48. Tier 2: the server sends `confirmation_question(sentence)` and waits **8 s** for a `prompt` or a key. 1 or „da" means red and a hand-over. Silence, an unclear reply or a hang-up: red and a hand-over. 2 or a clear „nu": the sentence and the reply go to the model as ordinary turns, and the match is stored as a tier 2 report for review. `alarms.needs_help` already parses the reply |
| `record_answer` | Stored through `voice` (the `answers` table) and kept in a `CallAnswers` for the call. A clear answer is never overwritten (`CallAnswers.record` returns False and the tool result says it was refused). Orientation is judged by the server. **Changed:** while an unclear answer has used fewer than **2** re-asks, the tool result names the question to ask again. A re-ask is used each time a tool result names that question, so the third unclear record of a question is final and certainty counts it as unclear. **Red from the rules acts at once** (04 §5, 03 §6): when the answers make `CallAnswers.severity` red, the server hands over immediately, with source `rules`, severity red and the `campaign_reason` wording as the reason |
| `raise_concern` | Raises the call's severity floor and never lowers it. It is stored as a status report (source `raise_concern`) when it is raised, so a later hang-up keeps it. A **red** concern hands over at once, with source `raise_concern`. *MVP simplification (my call):* a yellow concern or a yellow from the answers changes the senior's code when the call ends, at most 3 minutes later, not at the moment it is recorded as 03 §6 describes. Red is always immediate |
| `request_human` | **Changed meaning:** "the senior asked for a person, **or the agent judges the conversation can't go on**". Starts a hand-over, source `request_human`, code at least yellow, with the model's reason as the report reason |
| `end_call` | Refused until all three fields are recorded **and no unclear answer has a re-ask left** (my call, so the model can't skip the re-asks), or the call length limit is reached. The refusal names the missing question or the one to ask again. Accepted: the goodbye text is sent and the call is concluded |
| Dropped calls | Answered with low certainty (03 §6, §9; `final_severity` already supports it). The senior hanging up mid-conversation, the line dropping, and a model failure all conclude with the answers and concerns stored so far. The result is the higher of the starting severity and the rules' severity, at least the concerns' level, and yellow if that comes out green. **No redial:** 03 §5's redial is for calls nobody answered. So a senior who hangs up right after the greeting gets a yellow and an alert, as the spec intends. Today `settle` skips `conclude` for `dropped`; that changes for wellbeing calls |
| May close | All three recorded, and every unclear one has used its 2 re-asks (or none is unclear). The server then ends the call after the current turn (§4 step 5) |
| Key 9 | Hand-over at any time (built) |
| Call length limit | 3 min from `setup`. At the limit the server sends a fixed goodbye, concludes with the answers it has, and ends. The rules' last result is final |
| Recipients | Chosen by the server from the code; the model has no tool that notifies anyone |

**The hand-over data's reason (changed, only adds a value):** 04 §4.4 has `"alarm" | "key_9"`. Any hand-over that comes out of the conversation sends `"agent"`: a red `raise_concern`, `request_human`, or a red from the rules. The report source still says which one. No code reads the reason today besides the sender (`agent/relay.py`), so no client has to change.

**Test calls** (`trigger` `test`, from `scripts/place_call.py`) keep the S1 echo, unchanged (my call). The phone check for S4 and the "done when" run as a campaign call to a team member's number on `DIAL_ALLOWLIST`, which is what #49's "done when" describes.

## 6. How it fits the code

Package rules (backend AGENTS.md, ADR-005): `agent` imports only `voice` and `status`, holds no database session, and reaches the database only through `voice`'s session-owning functions. Anything in `calls` (ending, hand-over) reaches `agent` as a callable that `voice/router.py` builds, the way `hand_over_for` does today.

| Need | Where |
|---|---|
| The loop, tools, instructions, round rule, timers | `app/agent/` (`relay.py` grows into the loop, or splits into a few modules; builder's choice) |
| Provider client | `openai.AsyncOpenAI` in `agent/`; new dependency `openai` in `backend/pyproject.toml` |
| Settings | `DEEPINFRA_API_KEY` (secret, in Railway variables per 06 §4) and `AGENT_MODEL` (default `deepseek-ai/DeepSeek-V4-Pro`) on `Settings` and in `backend/.env.example`. The base URL is a constant |
| Store an answer | A session-owning wrapper in `voice/service.py` around `record_answer`, like `save_turn` |
| Call context | Read in `voice/router.py` with the greeting (`answer_context`) and passed to `serve` |
| Hand-over with a severity and a source | `calls.ending.begin_handover` derives the severity from the source today (`alarm_tier1` red, else yellow). A red `raise_concern` needs red with source `raise_concern`, so it takes the severity, or a mapping from the source. `hand_over_for` gains the `agent` escalation |
| Ending a completed call | `calls.ending.conclude(session, call, answers)`, reached through a callable from the router. Three gaps: it writes the mock card's summary („Apel simulat din aplicație…”), so a real call passes the model's `end_call` summary instead; it ignores concerns, so the stored `raise_concern` reports fold into the result (`final_severity` already takes `concern`); and it has no dropped branch. Today `end_completed` only moves the call state; it is replaced by this |
| Ending a dropped call | The hang-up arrives as a status callback in another request, after the session's memory is gone. So the dropped path reads the call's answers from the `answers` table and its concerns from its reports, then concludes as answered with low certainty. The model-failure path ends the call the same way. One way to build both: `conclude` always reads the answers and concerns from the database rather than taking them in memory, so the agent's ending, the mock card and a hang-up share one source |

The whole request path stays asynchronous (01 §8).

## 7. Spec changes that ship with the code

Per AGENTS.md ("contract changes move together"):

- **04 §5:** the provider is chosen (DeepInfra, `deepseek-ai/DeepSeek-V4-Pro`, a setting); the new `request_human` meaning; the two new instruction limits; up to 2 re-asks in the `record_answer` rule.
- **04 §4.3:** replace "Built so far (#48)" with the agent loop's behaviour.
- **04 §4.4:** reason `"alarm" | "key_9" | "agent"`.
- **03 §5:** "retry once" for an answered call becomes up to two re-asks per unclear question. The redial stays one.
- **03 §6:** note the MVP timing: a yellow takes effect when the call ends, red at once.
- **01 §8:** "written directly against the model provider's library" is no longer *proposed*.
- **06 §6:** S4's answer and date, with the text bake-off summary; the phone confirmation is still to do. **README:** close open question 4.

## 8. Tests

Fake model plus a scripted socket, no phone and no network (06 §5). The fake model replays scripted streams: text pieces and tool calls per round.

The cases listed in #49: the 04 §5 conversation; a refused `end_call`; a re-ask (and now a second re-ask, then giving up); a tier 1 phrase; tier 2 with yes, no and silence (8 s, with a fake clock); key 9; the time limit. Added by this design:
- an interrupt stops the stream and stores what was heard
- a model error or a 10 s timeout ends the call `dropped` with the fixed sentence
- a text-only round ends the turn, and a tool-only round goes round again, up to 3
- JSON-looking text is never sent
- a model `request_human` hands over with reason `agent`
- a red `raise_concern` hands over at once
- a red from the rules (unwell plus a wrong day) hands over at once, with source `rules`
- "may close" ends the call without `end_call`
- `end_call` is refused while an unclear answer has a re-ask left
- a hang-up after a clear „mi-e rău” ends yellow: `dropped`, concluded from the stored answers, no redial
- a hang-up right after the greeting ends yellow
- a test call still gets the echo

A live smoke test against DeepInfra stays out of CI; the bake-off script can be rerun by hand.

## 9. Left to the builder

- Module split inside `agent/`, and the shape of the cancellable turn task.
- Exact Romanian wording of the fixed sentences (model failure, a third round with no text, the time-limit goodbye) and of the instructions, within §4.
- How the conversation history is kept (a list of OpenAI-format messages per session is enough).
- Whether to set `service_tier: "priority"` (DeepInfra; about +50% price, a shorter wait). Off by default; turn it on if the phone test feels slow.
- How the concern floor is threaded into `conclude` (a parameter, or concerns stored as reports and read back).
