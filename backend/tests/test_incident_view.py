"""GET /incidents/{id} (04 §1): the queries without a database, then the whole view."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects import postgresql

from app.incident_view import calls_query, caregivers_query, incident_query
from app.models import (
    Call,
    CallTurn,
    Event,
    Grant,
    Incident,
    Role,
    StatusReport,
)

DAS, MEDIC, CAREGIVER = "+40700000001", "+40700000003", "+40700000004"


def sql(query) -> str:
    return str(
        query.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_both_names_come_from_users():
    q = sql(incident_query(uuid.uuid4()))
    assert q.count("LEFT OUTER JOIN users") == 2


def test_calls_window_is_open_until_resolved():
    since = datetime(2026, 10, 11, 12, tzinfo=UTC)
    assert "calls.created_at <=" not in sql(calls_query(uuid.uuid4(), since, None))
    closed = sql(calls_query(uuid.uuid4(), since, since + timedelta(hours=1)))
    assert "calls.created_at <=" in closed
    assert closed.rstrip().endswith("ORDER BY calls.created_at, calls.attempt")


def test_only_caregiver_grants():
    assert "grants.role = 'caregiver'" in sql(caregivers_query(uuid.uuid4()))


def signed_in(phone: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {phone}"}


async def test_the_whole_incident(client, db, add_user, add_senior):
    await add_user(DAS, Role.das, name="Ana DAS")
    await add_user(MEDIC, Role.medic)
    senior = await add_senior("+40700000101")
    senior.intercom_code = "12C"
    daughter = await add_user(CAREGIVER, name="Elena Pop")
    db.add(
        Grant(
            user_id=daughter.id,
            role=Role.caregiver,
            senior_id=senior.id,
            relation="fiică",
        )
    )
    now = datetime.now(UTC)

    def call(**kw) -> Call:
        return Call(
            senior_id=senior.id,
            trigger="watch",
            starting_severity="yellow",
            due_at=now,
            **kw,
        )

    first = call(state="unanswered")
    db.add(first)
    await db.flush()
    opening = call(
        state="handed_over",
        attempt=2,
        previous_call_id=first.id,
        handover_answered=True,
        final_severity="red",
    )
    db.add(opening)
    await db.flush()
    db.add_all(
        [
            Event(
                id=uuid.uuid4(),
                senior_id=senior.id,
                type="sos_button",
                measured_at=now,
                latitude=45.75,
                longitude=21.23,
                call_id=first.id,
            ),
            CallTurn(
                call_id=opening.id,
                position=1,
                speaker="senior",
                kind="speech",
                content="Am căzut și nu mă pot ridica",
            ),
            StatusReport(
                call_id=opening.id,
                source="alarm_tier1",
                severity="red",
                reason="căzătură",
                quote="Am căzut",
            ),
        ]
    )
    incident = Incident(
        senior_id=senior.id, opened_by_call_id=opening.id, reason="căzătură"
    )
    db.add(incident)
    await db.commit()

    r = await client.get(f"/api/incidents/{incident.id}", headers=signed_in(DAS))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "open"
    assert body["handover_answered"] is True
    assert body["senior"]["intercom_code"] == "12C"
    assert body["senior"]["phone_is_landline"] is False
    assert body["caregivers"] == [
        {"display_name": "Elena Pop", "phone_e164": CAREGIVER, "relation": "fiică"}
    ]
    # The event queued the first attempt; the opening call redialled it.
    assert body["event"]["type"] == "sos_button"
    assert body["event"]["latitude"] == 45.75
    assert [c["id"] for c in body["calls"]] == [str(first.id), str(opening.id)]
    last = body["calls"][1]
    assert last["turns"][0]["content"] == "Am căzut și nu mă pot ridica"
    assert last["reports"][0]["source"] == "alarm_tier1"


async def test_not_found_and_das_only(client, add_user):
    await add_user(DAS, Role.das)
    await add_user(MEDIC, Role.medic)
    missing = f"/api/incidents/{uuid.uuid4()}"
    r = await client.get(missing, headers=signed_in(DAS))
    assert r.status_code == 404
    assert r.json() == {"detail": {"reason": "not_found"}}
    r = await client.get(missing, headers=signed_in(MEDIC))
    assert r.status_code == 403
