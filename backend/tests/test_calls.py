import pytest

from app.status import Certainty
from app.voice.calls import (
    ENDED,
    LIVE,
    CallState,
    InvalidTransition,
    advance,
    ended_certainty,
    was_answered,
)


def test_happy_path():
    state = CallState.queued
    for new in (CallState.ringing, CallState.in_progress, CallState.completed):
        state = advance(state, new)
    assert state is CallState.completed


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (CallState.queued, CallState.failed),  # Twilio refused to place it
        (CallState.in_progress, CallState.unanswered),  # voicemail (04 §4.2)
    ],
)
def test_ways_out_of_a_live_call(current, new):
    assert advance(current, new) is new


def test_repeated_callback_is_a_no_op():
    assert advance(CallState.ringing, CallState.ringing) is CallState.ringing


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (CallState.queued, CallState.in_progress),
        (CallState.ringing, CallState.completed),
        (CallState.completed, CallState.in_progress),
        (CallState.unanswered, CallState.ringing),
    ],
)
def test_invalid_transitions(current, new):
    with pytest.raises(InvalidTransition):
        advance(current, new)


def test_live_and_ended_cover_every_state():
    assert LIVE | ENDED == set(CallState)
    assert not LIVE & ENDED


@pytest.mark.parametrize(
    ("state", "answered"),
    [
        (CallState.completed, True),
        (CallState.handed_over, True),
        (CallState.dropped, True),
        (CallState.unanswered, False),
        (CallState.failed, False),
    ],
)
def test_was_answered(state, answered):
    assert was_answered(state) is answered


def test_was_answered_refuses_a_live_call():
    with pytest.raises(ValueError):
        was_answered(CallState.in_progress)


def test_dropped_counts_as_low_certainty():
    assert ended_certainty(CallState.dropped, Certainty.high) is Certainty.low
    assert ended_certainty(CallState.completed, Certainty.high) is Certainty.high
