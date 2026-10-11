import uuid

import pytest

from app.calls import InvalidTransition
from app.incidents import (
    TRANSITIONS,
    UNRESOLVED,
    IncidentStatus,
    advance,
    opens_incident,
    resolve_refusal,
    take_refusal,
)
from app.status import Severity

OPEN = IncidentStatus.open
IN_PROGRESS = IncidentStatus.in_progress
RESOLVED = IncidentStatus.resolved


def test_take_then_resolve():
    assert advance(OPEN, IN_PROGRESS) is IN_PROGRESS
    assert advance(IN_PROGRESS, RESOLVED) is RESOLVED


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (OPEN, OPEN),
        (OPEN, RESOLVED),  # taken first, then resolved (UC-11)
        (IN_PROGRESS, IN_PROGRESS),  # a second taker is told who has it
        (IN_PROGRESS, OPEN),
        (RESOLVED, OPEN),  # reopening is deferred past the MVP
        (RESOLVED, IN_PROGRESS),
        (RESOLVED, RESOLVED),
    ],
)
def test_refused(current, new):
    with pytest.raises(InvalidTransition):
        advance(current, new)


def test_every_status_has_transitions():
    assert set(TRANSITIONS) == set(IncidentStatus)


def test_unresolved_are_the_statuses_that_can_still_move():
    assert UNRESOLVED == {status for status, nexts in TRANSITIONS.items() if nexts}


@pytest.mark.parametrize(
    ("result", "unresolved", "opens"),
    [
        (Severity.red, False, True),
        # A later red while one is open or in progress is added to it (G16).
        (Severity.red, True, False),
        (Severity.yellow, False, False),
        (Severity.green, False, False),
        (Severity.yellow, True, False),
    ],
)
def test_opens_incident(result, unresolved, opens):
    assert opens_incident(result, unresolved) is opens


ME, OTHER = uuid.uuid4(), uuid.uuid4()


@pytest.mark.parametrize(
    ("status", "taken_by", "reason"),
    [
        (IN_PROGRESS, ME, None),  # a repeat has no second effect (04 §0)
        (IN_PROGRESS, OTHER, "already_done"),  # told who has it (04 §2)
        (IN_PROGRESS, None, "already_done"),  # taken by answering the hand-over
        (RESOLVED, ME, "wrong_state"),
        (RESOLVED, OTHER, "wrong_state"),
    ],
)
def test_take_refusal(status, taken_by, reason):
    assert take_refusal(status, taken_by, ME) == reason


@pytest.mark.parametrize(
    ("status", "resolved_by", "outcome", "reason"),
    [
        (OPEN, None, None, "wrong_state"),  # taken first (UC-11)
        (RESOLVED, ME, "senior_ok", None),  # an exact repeat
        (RESOLVED, ME, "team_sent", "already_done"),
        (RESOLVED, OTHER, "senior_ok", "already_done"),
    ],
)
def test_resolve_refusal(status, resolved_by, outcome, reason):
    assert resolve_refusal(status, resolved_by, outcome, ME, "senior_ok") == reason
