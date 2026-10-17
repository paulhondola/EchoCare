"""Lifecycle of a call (03 §9).

Each attempt is its own call record; a redial is a new record pointing to the previous one.
The values are what the `call.state` column stores (05 §1).
"""

from enum import StrEnum

from app.status.engine import Certainty


class CallState(StrEnum):
    queued = "queued"
    ringing = "ringing"
    in_progress = "in_progress"
    unanswered = "unanswered"
    failed = "failed"
    completed = "completed"
    handed_over = "handed_over"
    dropped = "dropped"
    canceled = "canceled"


TRANSITIONS: dict[CallState, frozenset[CallState]] = {
    # failed: Twilio refused to place it, so it frees the senior's live slot (05 §3).
    # canceled: a campaign ended before the call went out (03 §9).
    CallState.queued: frozenset(
        {CallState.ringing, CallState.failed, CallState.canceled}
    ),
    CallState.ringing: frozenset(
        {CallState.in_progress, CallState.unanswered, CallState.failed}
    ),
    # unanswered: a machine picked up, found by voicemail detection (04 §4.2).
    CallState.in_progress: frozenset(
        {
            CallState.completed,
            CallState.handed_over,
            CallState.dropped,
            CallState.unanswered,
        }
    ),
    CallState.unanswered: frozenset(),
    CallState.failed: frozenset(),
    CallState.completed: frozenset(),
    CallState.handed_over: frozenset(),
    CallState.dropped: frozenset(),
    CallState.canceled: frozenset(),
}

# Live calls: at most one per senior, enforced by a partial unique index (05 §3).
LIVE = frozenset({CallState.queued, CallState.ringing, CallState.in_progress})
ENDED = frozenset(state for state, nexts in TRANSITIONS.items() if not nexts)
# On the way to an ended call these states mean someone picked up (03 §9).
ANSWERED = frozenset(
    {
        CallState.in_progress,
        CallState.completed,
        CallState.handed_over,
        CallState.dropped,
    }
)


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


# Twilio's CallStatus on a status callback, as our state (04 §4.2). `initiated` and
# `queued` are Twilio's own dialing steps and change nothing here.
TWILIO_STATUSES: dict[str, CallState] = {
    "ringing": CallState.ringing,
    "in-progress": CallState.in_progress,
    # Twilio says completed whoever ended the call. A call our side closed is already
    # completed (the relay marks it before its `end`), and an ended call stays as it
    # ended; so a completed that still moves a call is a hang-up or a lost line (03 §9).
    "completed": CallState.dropped,
    "busy": CallState.unanswered,
    "no-answer": CallState.unanswered,
    "canceled": CallState.unanswered,
    "failed": CallState.failed,
}
TWILIO_DIALING = frozenset({"queued", "initiated"})

# What voicemail detection's AnsweredBy says when no person picked up (04 §4.2).
MACHINE_PREFIXES = ("machine_", "fax")


def reachable(current: CallState, new: CallState) -> bool:
    """Whether `new` lies ahead of `current` through any allowed transitions."""
    seen, frontier = set(), [current]
    while frontier:
        for state in TRANSITIONS[frontier.pop()]:
            if state is new:
                return True
            if state not in seen:
                seen.add(state)
                frontier.append(state)
    return False


def after_callback(current: CallState, new: CallState | None) -> CallState | None:
    """The state a callback moves the call to, or None when it changes nothing.

    Twilio's callbacks can arrive late, twice or out of order, and one can be lost: a
    `completed` without the `in-progress` before it still means the call was answered.
    So a callback may skip ahead, never go back, and an ended call stays as it ended.
    """
    # A state this copy does not know, written by a newer one, is left alone.
    if current not in TRANSITIONS or new is None or new is current:
        return None
    if not reachable(current, new):
        return None
    return new


def answered_by_machine(answered_by: str) -> bool:
    return answered_by.startswith(MACHINE_PREFIXES)
