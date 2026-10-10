"""Lifecycle of a call (03 §9).

Each attempt is its own call record; a redial is a new record pointing to the previous one.
The values are what the `call.state` column stores (05 §1).
"""

from enum import StrEnum

from app.status import Certainty


class CallState(StrEnum):
    queued = "queued"
    ringing = "ringing"
    in_progress = "in_progress"
    unanswered = "unanswered"
    failed = "failed"
    completed = "completed"
    handed_over = "handed_over"
    dropped = "dropped"


TRANSITIONS: dict[CallState, frozenset[CallState]] = {
    CallState.queued: frozenset({CallState.ringing}),
    CallState.ringing: frozenset(
        {CallState.in_progress, CallState.unanswered, CallState.failed}
    ),
    CallState.in_progress: frozenset(
        {CallState.completed, CallState.handed_over, CallState.dropped}
    ),
    CallState.unanswered: frozenset(),
    CallState.failed: frozenset(),
    CallState.completed: frozenset(),
    CallState.handed_over: frozenset(),
    CallState.dropped: frozenset(),
}

# Live calls: at most one per senior, enforced by a partial unique index (05 §3).
LIVE = frozenset({CallState.queued, CallState.ringing, CallState.in_progress})
ENDED = frozenset(state for state, nexts in TRANSITIONS.items() if not nexts)


class InvalidTransition(ValueError):
    pass


def advance(current: CallState, new: CallState) -> CallState:
    """Move a call to its next state. A repeated callback for the same state is a no-op."""
    if new is current:
        return current
    if new not in TRANSITIONS[current]:
        raise InvalidTransition(f"call cannot go from {current} to {new}")
    return new


def was_answered(state: CallState) -> bool:
    """Whether an ended call counts as answered for the status engine (03 §9)."""
    if state not in ENDED:
        raise ValueError(f"call in {state} has not ended")
    return state in {CallState.completed, CallState.handed_over, CallState.dropped}


def ended_certainty(state: CallState, computed: Certainty) -> Certainty:
    """A dropped call counts as answered with low certainty, whatever the rules computed."""
    if state is CallState.dropped:
        return Certainty.low
    return computed
