"""GET /incidents (04 §1): the status filter and the query, without a database."""

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.incidents import IncidentStatus
from app.main import incidents_query, parse_statuses


def sql(statuses) -> str:
    return str(
        incidents_query(statuses).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


@pytest.mark.parametrize("raw", [None, ""])
def test_no_filter_means_any_status(raw):
    assert parse_statuses(raw) is None
    assert "WHERE" not in sql(None)


def test_filter_is_comma_separated():
    assert parse_statuses("open, in_progress") == {
        IncidentStatus.open,
        IncidentStatus.in_progress,
    }


def test_unknown_status_is_refused():
    with pytest.raises(HTTPException) as e:
        parse_statuses("open,closed")
    assert e.value.status_code == 422


def test_filter_matches_stored_names():
    where = sql({IncidentStatus.in_progress}).split("WHERE")[1]
    assert "'in_progress'" in where


def test_newest_first():
    assert sql(None).rstrip().endswith("ORDER BY incidents.opened_at DESC")
