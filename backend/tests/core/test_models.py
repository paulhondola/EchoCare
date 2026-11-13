"""The schema (05 §3): compiled for PostgreSQL without a database, then against one."""

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.db import Base
from app.incidents.models import UNRESOLVED
from app.models import SENIOR_ROLES, Call, Event, EventType, Grant, Role
from app.status.engine import Severity
from app.voice.calls import LIVE

BACKEND = Path(__file__).parents[2]
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
        "watch_readings",
        "senior_summaries",
        "events",
        "campaigns",
        "calls",
        "call_turns",
        "answers",
        "status_reports",
        "senior_statuses",
        "incidents",
        "push_tokens",
        "medical_records",
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
    # Named before the naming convention, in 5d0c8c3a7f21.
    assert "CONSTRAINT senior_only_for_senior_roles CHECK" in sql
    for role in SENIOR_ROLES:
        assert f"'{role.name}'" in sql


def test_one_current_code_and_watch_state_per_senior():
    assert "PRIMARY KEY (senior_id)" in create_table("senior_statuses")
    assert "PRIMARY KEY (senior_id)" in create_table("watch_states")


def test_event_id_comes_from_the_device():
    # A resent event hits the primary key instead of getting a fresh id (05 §3).
    assert Event.__table__.c.id.server_default is None
    assert "id UUID DEFAULT uuidv7() NOT NULL" in create_table("calls")


def test_at_most_one_senior_grant_per_user():
    # AL7: a couple sharing one mobile gives the second senior no app role.
    sql = create_index("grants", "uq_grants_one_senior_per_user")
    assert sql.startswith("CREATE UNIQUE INDEX uq_grants_one_senior_per_user")
    assert sql.endswith("ON grants (user_id) WHERE role = 'senior'")


def test_grants_name_a_real_senior():
    # AL6: the foreign key arrived with the seniors table.
    assert "FOREIGN KEY(senior_id) REFERENCES seniors (id) ON DELETE CASCADE" in (
        create_table("grants")
    )


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


def test_an_unknown_name_reads_back_as_a_string():
    # Written by a newer copy during a deploy, or before a rollback (ADR-001 §2.3).
    read = Event.__table__.c.type.type.process_result_value
    assert read("sos_button", DIALECT) is EventType.sos_button
    assert read("fall", DIALECT) == "fall"
    assert (
        Call.__table__.c.final_severity.type.process_result_value("red", DIALECT)
        is Severity.red
    )


def test_models_match_the_migration(migrated):
    # `alembic check` fails when autogenerate would add anything (auth-layer §4).
    subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=BACKEND, check=True)


async def test_ids_are_uuid_v7(add_user):
    user = await add_user("+40700000001")
    assert user.id.version == 7


async def test_one_grant_per_role(db, add_user):
    user = await add_user("+40700000001", Role.das)
    db.add(Grant(user_id=user.id, role=Role.das))
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.parametrize(
    ("role", "senior_id"),
    [
        (Role.caregiver, None),  # a caregiver grant names its senior
        (Role.senior, None),
        (Role.das, uuid.uuid4()),  # a staff grant names none
        ("boss", None),  # only the four roles
    ],
)
async def test_grant_checks(db, add_user, role, senior_id):
    user = await add_user("+40700000001")
    db.add(Grant(user_id=user.id, role=role, senior_id=senior_id))
    with pytest.raises(IntegrityError):
        await db.commit()
