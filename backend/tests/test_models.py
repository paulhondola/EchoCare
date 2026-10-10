"""The schema, compiled for PostgreSQL without a database (05 §3)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.calls import LIVE
from app.db import Base
from app.incidents import UNRESOLVED
from app.models import SENIOR_ROLES, Call, Event, new_id
from app.status import Severity

DIALECT = postgresql.dialect()


def ddl(element) -> str:
    return str(element.compile(dialect=DIALECT))


def create_table(name: str) -> str:
    return ddl(CreateTable(Base.metadata.tables[name]))


def create_index(table: str, name: str) -> str:
    (index,) = (i for i in Base.metadata.tables[table].indexes if i.name == name)
    return ddl(CreateIndex(index))


def test_every_entity_has_a_table():
    assert set(Base.metadata.tables) == {
        "users",
        "grants",
        "seniors",
        "consents",
        "watch_states",
        "events",
        "campaigns",
        "calls",
        "call_turns",
        "answers",
        "status_reports",
        "senior_statuses",
        "incidents",
        "push_tokens",
    }


@pytest.mark.parametrize("table", Base.metadata.sorted_tables, ids=lambda t: t.name)
def test_table_compiles(table):
    ddl(CreateTable(table))
    for index in table.indexes:
        ddl(CreateIndex(index))


def test_unique_phone_number():
    assert "UNIQUE (phone_e164)" in create_table("users")


def test_at_most_one_on_duty():
    sql = create_index("users", "uq_users_on_duty")
    assert sql.startswith("CREATE UNIQUE INDEX uq_users_on_duty ON users (on_duty)")
    assert sql.endswith("WHERE on_duty")


def test_one_live_call_per_senior():
    sql = create_index("calls", "uq_calls_live_senior")
    assert sql.startswith("CREATE UNIQUE INDEX uq_calls_live_senior ON calls")
    assert "(senior_id)" in sql
    assert sql.endswith("WHERE state IN ('in_progress', 'queued', 'ringing')")
    assert {state.name for state in LIVE} == {"in_progress", "queued", "ringing"}


def test_scheduler_queue_index():
    sql = create_index("calls", "ix_calls_queued_due_at")
    assert "UNIQUE" not in sql
    assert sql.endswith("ON calls (due_at) WHERE state IN ('queued')")


def test_one_unresolved_incident_per_senior():
    sql = create_index("incidents", "uq_incidents_unresolved_senior")
    assert sql.startswith("CREATE UNIQUE INDEX")
    assert sql.endswith("WHERE status IN ('in_progress', 'open')")
    assert {status.name for status in UNRESOLVED} == {"in_progress", "open"}


def test_resolving_needs_an_outcome():
    sql = create_table("incidents")
    assert "CONSTRAINT ck_incidents_resolved_has_outcome CHECK" in sql


def test_one_grant_per_role_and_senior_even_without_a_senior():
    # Plain UNIQUE would let a user hold the das grant twice: NULL senior_ids differ.
    sql = create_table("grants")
    assert "UNIQUE NULLS NOT DISTINCT (user_id, role, senior_id)" in sql


def test_only_caregiver_and_senior_grants_name_a_senior():
    sql = create_table("grants")
    assert "CONSTRAINT ck_grants_senior_only_for_senior_roles CHECK" in sql
    for role in SENIOR_ROLES:
        assert f"'{role.name}'" in sql


def test_one_current_code_and_watch_state_per_senior():
    assert "PRIMARY KEY (senior_id)" in create_table("senior_statuses")
    assert "PRIMARY KEY (senior_id)" in create_table("watch_states")


def test_event_id_comes_from_the_device():
    # A resent event hits the primary key instead of getting a fresh id (05 §3).
    assert Event.__table__.c.id.default is None
    assert Call.__table__.c.id.default is not None


def test_enums_are_plain_strings_without_a_check():
    # Adding a value later must not need a migration (ADR-001 §2.3).
    sql = create_table("calls")
    assert "final_severity VARCHAR(32)" in sql
    assert "state VARCHAR(32)" in sql
    assert "CHECK" not in sql


def test_severity_is_stored_by_name():
    query = select(Call.id).where(Call.final_severity == Severity.red)
    sql = str(query.compile(dialect=DIALECT, compile_kwargs={"literal_binds": True}))
    assert "calls.final_severity = 'red'" in sql
    assert Call.__table__.c.final_severity.type.enums == ["green", "yellow", "red"]


def test_new_ids_are_time_ordered():
    ids = [new_id() for _ in range(50)]
    assert all(i.version == 7 for i in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    assert isinstance(ids[0], uuid.UUID)
