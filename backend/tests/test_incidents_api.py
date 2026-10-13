"""The incident endpoints (04 §1, §2): the query without a database, then the
commands against one."""

import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.incidents import IncidentStatus, incidents_query, parse_statuses
from app.models import Incident, Role


def sql(statuses) -> str:
    return str(
        incidents_query(statuses).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def outer(query: str) -> str:
    """The outer query's joins and WHERE, past the hand-over subquery's own WHERE."""
    return query.split("FROM incidents JOIN")[1]


@pytest.mark.parametrize("raw", [None, ""])
def test_no_filter_means_any_status(raw):
    assert parse_statuses(raw) is None
    assert "WHERE" not in outer(sql(None))


def test_filter_is_comma_separated():
    assert parse_statuses("open, in_progress") == {
        IncidentStatus.open,
        IncidentStatus.in_progress,
    }


def test_unknown_status_is_refused():
    with pytest.raises(HTTPException) as e:
        parse_statuses("open,closed")
    assert e.value.status_code == 422
    assert e.value.detail == {"reason": "unknown_status"}  # 04 §0


def test_filter_matches_stored_names():
    where = outer(sql({IncidentStatus.in_progress})).split("WHERE")[1]
    assert "'in_progress'" in where


def test_newest_first():
    assert sql(None).rstrip().endswith("ORDER BY incidents.opened_at DESC")


def test_one_incident_by_id():
    incident_id = uuid.uuid4()
    where = outer(
        str(incidents_query(None, incident_id).compile(dialect=postgresql.dialect()))
    ).split("WHERE")[1]
    assert "incidents.id =" in where


DAS, OTHER_DAS, MEDIC = "+40700000001", "+40700000002", "+40700000003"
RESOLUTION = {"outcome": "senior_ok", "note": "  A răspuns, e bine.  "}


def signed_in(phone: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {phone}"}


@pytest.fixture
async def incident(db, add_user, add_senior) -> Incident:
    await add_user(DAS, Role.das, name="Ana DAS")
    await add_user(OTHER_DAS, Role.das, name="Ion DAS")
    await add_user(MEDIC, Role.medic)
    senior = await add_senior("+40700000101")
    row = Incident(senior_id=senior.id, reason="durere în piept")
    db.add(row)
    await db.commit()
    return row


async def take(client, incident_id, phone=DAS):
    return await client.post(
        f"/api/incidents/{incident_id}/take", headers=signed_in(phone)
    )


async def resolve(client, incident_id, phone=DAS, body=RESOLUTION):
    return await client.post(
        f"/api/incidents/{incident_id}/resolve", json=body, headers=signed_in(phone)
    )


async def stored(db, incident_id) -> Incident:
    db.expire_all()
    return await db.scalar(select(Incident).where(Incident.id == incident_id))


async def test_take_then_resolve(client, db, incident):
    r = await take(client, incident.id)
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"
    assert r.json()["taken_by_name"] == "Ana DAS"
    assert r.json()["taken_at"] is not None

    r = await resolve(client, incident.id, phone=OTHER_DAS)  # any DAS employee
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    row = await stored(db, incident.id)
    assert row.outcome == "senior_ok"
    assert row.note == "A răspuns, e bine."
    assert row.resolved_at is not None


async def test_a_second_taker_is_told_who_has_it(client, db, incident):
    await take(client, incident.id)
    r = await take(client, incident.id, phone=OTHER_DAS)
    assert r.status_code == 409
    assert r.json() == {
        "detail": {"reason": "already_done", "taken_by_name": "Ana DAS"}
    }
    assert (await stored(db, incident.id)).taken_by is not None


async def test_repeats_have_no_second_effect(client, db, incident):
    first = (await take(client, incident.id)).json()
    again = await take(client, incident.id)
    assert again.status_code == 200
    assert again.json() == first

    resolved = (await resolve(client, incident.id)).json()
    again = await resolve(client, incident.id)
    assert again.status_code == 200
    assert again.json() == resolved


async def test_wrong_state(client, incident):
    r = await resolve(client, incident.id)  # still open: take it first
    assert r.status_code == 409
    assert r.json() == {"detail": {"reason": "wrong_state"}}

    await take(client, incident.id)
    await resolve(client, incident.id)
    r = await take(client, incident.id)
    assert r.json() == {"detail": {"reason": "wrong_state"}}
    r = await resolve(client, incident.id, body={**RESOLUTION, "outcome": "team_sent"})
    assert r.json() == {"detail": {"reason": "already_done"}}


async def test_old_resolved_incidents_leave_the_list(client, db, incident):
    await take(client, incident.id)
    await resolve(client, incident.id)
    listed = (await client.get("/api/incidents", headers=signed_in(DAS))).json()
    assert [i["id"] for i in listed] == [str(incident.id)]
    row = await stored(db, incident.id)
    row.resolved_at -= timedelta(days=2)
    await db.commit()
    assert (await client.get("/api/incidents", headers=signed_in(DAS))).json() == []


async def test_only_das(client, incident):
    r = await take(client, incident.id, phone=MEDIC)
    assert r.status_code == 403
    assert r.json() == {"detail": {"reason": "not_allowed"}}


async def test_unknown_incident(client, incident):
    r = await take(client, uuid.uuid4())
    assert r.status_code == 404
    assert r.json() == {"detail": {"reason": "not_found"}}


@pytest.mark.parametrize(
    "body",
    [
        {"outcome": "senior_ok"},  # a note is required (UC-11)
        {"outcome": "senior_ok", "note": "   "},
        {"outcome": "fixed", "note": "x"},  # only the five outcomes
    ],
)
async def test_invalid_resolutions(client, db, incident, body):
    await take(client, incident.id)
    r = await resolve(client, incident.id, body=body)
    assert r.status_code == 422
    assert (await stored(db, incident.id)).status == IncidentStatus.in_progress
