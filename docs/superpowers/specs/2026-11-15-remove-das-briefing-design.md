# Remove the spoken DAS briefing from the hand-over

A small change. Reverses feature 3 of [2026-11-14-demo-showcase-design.md](2026-11-14-demo-showcase-design.md) §6.

## Intent

When the on-duty DAS phone picks up a hand-over, it hears the briefing first: a spoken summary of about 10 seconds in the AI's voice („Predare EchoCare. … Vă conectez.”). The senior waits on hold while it plays. We want the transfer to be direct: DAS answers and is talking to the senior straight away.

## Goals, non-goals

- Goal: `/voice/handoff-answered` connects the two right away. It still records `handover_answered` and gives the senior's open incident to the employee who answered.
- Non-goal: the AI's line to the senior before the transfer („Vă conectez acum cu un operator, rămâneți pe fir.”) stays as it is.
- Non-goal: the briefing on the dashboard (the senior's latest summary, `summary` on `GET /incidents/{id}`, `Briefing.svelte`) stays. DAS can still read who is calling and why on the incident card.
- Anti-goal: anything that could make a connect fail or slow down. The response after the answer is the empty TwiML used before 2026-11-14.

## Approaches

1. **Remove the briefing only (picked).** DAS is connected at once and reads who is calling on the dashboard.
2. Also remove the AI's "connecting you" line. Rejected: the senior would hear a ring with no warning.
3. Remove both. Rejected for the same reason.

## Design

- `voice/router.py` `handoff_answered`: drop the briefing step and return `twiml("")` after the commit. The error path for a database failure is unchanged.
- Delete `briefing()` and `BRIEFING_SUMMARY_WORDS` from `voice/dialogue.py`, and `handover_briefing()` from `voice/service.py`, together with the imports that only they used (`latest_summary` and `read_content` in `voice/service.py`, and `re` in `dialogue.py` if nothing else uses it).
- Tests: delete `tests/voice/test_briefing.py`. In `tests/voice/test_handover.py`, the answered test asserts an empty response instead of „Predare EchoCare.”, and `test_a_failing_briefing_still_connects` and `test_no_briefing_after_the_database_failed` are deleted.
- Spec: in the "Hand-over answered" row of `04-interfaces.md` §4.4, remove the sentence about the briefing. Line 38 (`summary`, "for the DAS briefing") describes the dashboard and stays.
- No API contract change, so no client changes. Old and new API copies can overlap during the deploy.

## Left to the builder

- `HANDOVER_LIVE` (90 s, `calls/service.py`) stays: the ring and DAS's first sentence can still take most of a minute. Only its comment, which mentions the briefing, is updated (my call).
- The demo-showcase design and plan are history and are left as written.
- Deploying redeploys `api` and drops live calls, so ship outside a demo.
