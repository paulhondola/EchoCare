import uuid

import pytest

from app.incidents import (
    IncidentStatus,
    opens_incident,
    resolve_refusal,
    take_refusal,
)
from app.status import Severity

OPEN = IncidentStatus.open
IN_PROGRESS = IncidentStatus.in_progress
RESOLVED = IncidentStatus.resolved


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
    ("status", "done", "reason"),
    [
        (OPEN, (None, None, None), "wrong_state"),  # taken first (UC-11)
        (RESOLVED, (ME, "senior_ok", "e bine"), None),  # an exact repeat
        (RESOLVED, (ME, "team_sent", "e bine"), "already_done"),
        (RESOLVED, (ME, "senior_ok", "alta notă"), "already_done"),  # note not lost
        (RESOLVED, (OTHER, "senior_ok", "e bine"), "already_done"),
    ],
)
def test_resolve_refusal(status, done, reason):
    assert resolve_refusal(status, done, (ME, "senior_ok", "e bine")) == reason
