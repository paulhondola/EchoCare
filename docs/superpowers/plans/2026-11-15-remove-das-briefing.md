# Remove the spoken DAS briefing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When DAS answers a hand-over, connect them straight to the senior, with no spoken briefing first.

**Architecture:** `/voice/handoff-answered` returns empty TwiML after recording the answer and taking the incident, as it did before 2026-11-14. The briefing builder and its loader are deleted.

**Tech Stack:** Python 3.14, FastAPI, pytest, uv, ruff (`backend/`).

**Spec:** [docs/superpowers/specs/2026-11-15-remove-das-briefing-design.md](../specs/2026-11-15-remove-das-briefing-design.md)

## Global Constraints

- No API contract change; nothing renamed or dropped that a client calls (ADR-001 §2.3).
- Keep the AI's „Vă conectez acum cu un operator, rămâneți pe fir.” line to the senior.
- Keep the dashboard briefing: `summary` on `GET /incidents/{id}` (04 line 38), `seniors/router.py` briefing endpoint, `Briefing.svelte`.
- `HANDOVER_LIVE` stays `timedelta(seconds=90)`.
- Run every command from `backend/`. Commit with the hooks on.

## Review Focus

1. The database fails while recording the answer → still empty TwiML, so Twilio connects. Pinned by `test_a_failed_database_still_connects` (Task 1 Step 1, rewritten from the old briefing test).
2. The answered response contains no `<Say>` at all, not just no „Predare” → pinned by the rewritten test in Task 1.
3. No leftover import of `handover_briefing` or `briefing` anywhere → `ruff check` and the full `pytest` run in Task 1.

---

### Task 1: Connect DAS without a briefing

**Files:**
- Modify: `backend/app/voice/router.py` (import list ~line 65; `handoff_answered` ~lines 371–394)
- Modify: `backend/app/voice/service.py` (imports lines 26 and 29; delete `handover_briefing` ~lines 508–533)
- Modify: `backend/app/voice/dialogue.py` (delete `BRIEFING_SUMMARY_WORDS` and `briefing()` ~lines 88–115; delete `import re` if nothing else uses it)
- Modify: `backend/app/calls/service.py:26-28` (comment only)
- Modify: `docs/specs/echocare/04-interfaces.md:167`
- Delete: `backend/tests/voice/test_briefing.py`
- Test: `backend/tests/voice/test_handover.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `handoff_answered(call, user, _, session) -> Response` keeps its signature; the body is always empty TwiML (`twiml("")`).

- [ ] **Step 1: Rewrite the answered test to expect a direct connect**

In `test_answering_takes_the_incident`, replace the comment and the two `said` lines with:

```python
    # DAS is connected straight to the senior (design 2026-11-15)
    assert len(root) == 0
```

Delete `test_a_failing_briefing_still_connects`; it tests only the briefing.

Rename `test_no_briefing_after_the_database_failed` to `test_a_failed_database_still_connects`. Keep its `down` patch of `app.voice.router.answer_handover` and its `len(twiml(r)) == 0` assertion. Drop the `asked` list, the fake `briefing` and its `monkeypatch` line. Comment: `# DAS is on the line: connect even when the answer can't be written`.

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/voice/test_handover.py::test_answering_takes_the_incident -v`
Expected: FAIL, the response still holds a `<Say>`.

- [ ] **Step 3: Drop the briefing from `handoff_answered`**

After `await session.commit()` and the unchanged `except` block, return `twiml("")`. Remove the briefing `try`/`except` and its comment. Docstring becomes: the incident is taken by the one we rang and Twilio connects the two (04 §4.4 step 5). Remove `handover_briefing` from the `app.voice.service` import list.

- [ ] **Step 4: Delete the briefing code**

Delete `handover_briefing` from `voice/service.py`, along with the `latest_summary, read_content` import and the `from app.voice.dialogue import briefing` import. Delete `BRIEFING_SUMMARY_WORDS`, its comment and `briefing()` from `voice/dialogue.py`, plus `import re` if it is now unused. Delete `tests/voice/test_briefing.py`.

- [ ] **Step 5: Fix the comment and the spec**

`calls/service.py` comment: "the briefing, the ring and DAS's first sentence" → "the ring and DAS's first sentence".
`04-interfaces.md` line 167: delete the sentence "Says a short briefing to the employee (who, address, the senior's words from the call's reason, the summary's first sentence), then connects; any failure building it connects silently (design 2026-11-14 §6)." and start the row with "Connects the two."

- [ ] **Step 6: Run the checks**

Run: `uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run pytest`
Expected: all pass; `grep -rn "handover_briefing\|BRIEFING_SUMMARY\|import briefing" app tests` prints nothing.

- [ ] **Step 7: Commit**

```bash
git add -A app tests ../docs/specs/echocare/04-interfaces.md ../docs/superpowers
git commit -m "voice: connect DAS without a spoken briefing (04 §4.4)"
```
