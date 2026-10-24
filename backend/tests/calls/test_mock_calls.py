"""The mock campaign call, read and answered from the senior's app (design §4.2, §5)."""

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, update

from app.calls import mock
from app.core.settings import AppEnv
from app.models import (
    Answer,
    Call,
    CallTrigger,
    Campaign,
    Consent,
    EnrollmentState,
    Grant,
    Role,
    Senior,
    WelcomeOutcome,
)
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.dialogue import CARD_CONSENT_TEXT, CARD_CONSENT_VERSION

DAS, MEDIC, NO_GRANT = "+40700000001", "+40700000002", "+40700000009"
SENIOR, OTHER_SENIOR, CAREGIVER = "+40700000101", "+40700000102", "+40700000103"
WELCOMED = "+40700000106"  # the senior of `welcome_card`

# Everyone but the senior whose call it is (06 §5): each role, a number with no grant,
# signed out (None).
NOT_THE_SENIOR = [MEDIC, CAREGIVER, DAS, NO_GRANT, None]


def signed_in(token):
    return {} if token is None else {"Authorization": f"Bearer {token}"}


async def card(client, token=SENIOR):
    return await client.get("/api/profile/mock-call", headers=signed_in(token))


async def answer(client, call_id, body, token=SENIOR):
    return await client.post(
        f"/api/calls/{call_id}/mock-answer", json=body, headers=signed_in(token)
    )


async def reports(client, call_id):
    """The call's status reports (05 §2), as DAS reads them: (source, severity, reason)."""
    t = (
        await client.get(f"/api/calls/{call_id}/transcript", headers=signed_in(DAS))
    ).json()
    return [(r["source"], r["severity"], r["reason"]) for r in t["reports"]]


@pytest.fixture
async def queued(client, db, add_user, add_active_senior):
    """A DAS user, a medic, an active senior with a senior grant and a caregiver, and a
    cold, yellow campaign started through the API. Returns the senior."""
    await add_user(DAS, Role.das, name="DAS Test")
    medic = await add_user(MEDIC, Role.medic)
    senior = await add_active_senior(SENIOR, medic=medic)
    caregiver = await add_user(CAREGIVER)
    db.add(Grant(user_id=caregiver.id, role=Role.caregiver, senior_id=senior.id))
    await db.commit()
    r = await client.post(
        "/api/campaigns",
        json={"kind": "cold", "level": "yellow"},
        headers=signed_in(DAS),
    )
    assert r.status_code == 201
    return senior


async def test_the_card_shows_the_due_campaign_call(client, queued):
    r = await card(client)
    assert r.status_code == 200
    assert r.json() | {"call_id": None} == {
        "call_id": None,
        "trigger": "campaign",
        "campaign_kind": "cold",
        "campaign_level": "yellow",
        "consent_text": None,
        "text_version": None,
    }


async def test_answers_go_through_the_rules(client, db, queued, monkeypatch):
    monkeypatch.setattr(
        "app.calls.ending.today_in_bucharest", lambda: date(2026, 10, 15)
    )
    call_id = (await card(client)).json()["call_id"]
    r = await answer(
        client, call_id, {"feeling": "unwell", "day": "joi", "shelter": "no"}
    )
    assert r.status_code == 204
    t = (
        await client.get(f"/api/calls/{call_id}/transcript", headers=signed_in(DAS))
    ).json()
    assert t["state"] == "completed" and t["final_severity"] == "red"
    assert [a["field"] for a in t["answers"]] == ["feeling", "orientation", "shelter"]
    assert t["turns"][1]["content"].endswith("azi e cod galben de ger. Cum vă simțiți?")
    incidents = await client.get("/api/incidents", headers=signed_in(DAS))
    assert incidents.json()[0]["reason"] == "Se simte rău și nu are căldură în casă"
    assert (await card(client)).status_code == 204


@pytest.mark.parametrize(
    ("body", "goodbye"),
    [
        (
            {"feeling": "unwell", "day": "joi", "shelter": "no"},
            "Doamna Maria, un dispecer DAS a fost anunțat.",
        ),
        (
            {"feeling": "ok", "day": "joi", "shelter": "yes"},
            "Vă mulțumesc, doamna Maria. O zi bună!",
        ),
    ],
)
async def test_the_transcript_reads_like_a_call(
    client, queued, monkeypatch, body, goodbye
):
    monkeypatch.setattr(
        "app.calls.ending.today_in_bucharest", lambda: date(2026, 10, 15)
    )
    call_id = (await card(client)).json()["call_id"]
    assert (await answer(client, call_id, body)).status_code == 204
    t = (
        await client.get(f"/api/calls/{call_id}/transcript", headers=signed_in(DAS))
    ).json()
    said = {"ok": "Bine", "unwell": "Rău", "yes": "Da", "no": "Nu"}
    assert [
        (turn["speaker"], turn["kind"], turn["content"]) for turn in t["turns"]
    ] == [
        ("system", "speech", "Apel simulat din aplicație, fără linie telefonică."),
        (
            "agent",
            "speech",
            (
                "Bună ziua, doamna Maria. Sunt asistentul automat al DAS Timișoara. "
                "Vă sunăm pentru că azi e cod galben de ger. Cum vă simțiți?"
            ),
        ),
        ("senior", "speech", said[body["feeling"]]),
        ("agent", "speech", "Ce zi este azi?"),
        ("senior", "speech", "Joi"),
        ("agent", "speech", "Aveți căldură în casă?"),
        ("senior", "speech", said[body["shelter"]]),
        ("agent", "speech", goodbye),
    ]


async def test_a_second_tap_is_already_done(client, db, queued):
    call_id = (await card(client)).json()["call_id"]
    body = {"feeling": "ok", "day": "unknown", "shelter": "yes"}
    assert (await answer(client, call_id, body)).status_code == 204
    again = await answer(client, call_id, body)
    assert (again.status_code, again.json()) == (
        409,
        {"detail": {"reason": "already_done"}},
    )
    assert await db.scalar(select(func.count()).select_from(Answer)) == 3
    assert [source for source, *_ in await reports(client, call_id)] == ["rules"]


async def test_not_now_hides_the_card_until_the_redial(client, queued):
    call_id = (await card(client)).json()["call_id"]
    assert (await answer(client, call_id, {"declined": True})).status_code == 204
    assert (await card(client)).status_code == 204
    redial = (
        await client.get(f"/api/seniors/{queued.id}/calls", headers=signed_in(SENIOR))
    ).json()[0]
    assert redial["state"] == "queued"
    r = await answer(client, redial["id"], {"declined": True})
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})


async def test_not_now_is_written_to_the_transcript(client, queued):
    call_id = (await card(client)).json()["call_id"]
    assert (await answer(client, call_id, {"declined": True})).status_code == 204
    t = (
        await client.get(f"/api/calls/{call_id}/transcript", headers=signed_in(DAS))
    ).json()
    assert (t["state"], t["started_at"], t["answers"]) == ("unanswered", None, [])
    assert t["ended_at"] is not None
    assert [(turn["speaker"], turn["content"]) for turn in t["turns"]] == [
        ("system", "Apel simulat din aplicație, fără linie telefonică."),
        ("system", "Seniorul a ales „Nu acum”."),
    ]
    assert await reports(client, call_id) == [
        ("unanswered", "green", "Nu a răspuns la prima încercare")
    ]


async def test_not_now_twice_ends_yellow(client, db, queued):
    first = (await card(client)).json()["call_id"]
    assert (await answer(client, first, {"declined": True})).status_code == 204
    await db.execute(
        update(Call)
        .where(Call.previous_call_id == uuid.UUID(first))
        .values(due_at=datetime.now(UTC))
    )
    await db.commit()
    redial = (await card(client)).json()["call_id"]
    assert redial != first
    assert (await answer(client, redial, {"declined": True})).status_code == 204
    t = (
        await client.get(f"/api/calls/{redial}/transcript", headers=signed_in(DAS))
    ).json()
    assert (t["state"], t["final_severity"], t["reason"]) == (
        "unanswered",
        "yellow",
        "Nu a răspuns de două ori",
    )
    assert await reports(client, redial) == [
        ("unanswered", "yellow", "Nu a răspuns de două ori")
    ]
    assert (await card(client)).status_code == 204


async def test_missing_answers_are_incomplete(client, db, queued):
    call_id = (await card(client)).json()["call_id"]
    r = await answer(client, call_id, {"feeling": "ok"})
    assert (r.status_code, r.json()) == (
        422,
        {"detail": {"reason": "incomplete", "missing": ["day", "shelter"]}},
    )
    assert await db.scalar(select(Call.state).where(Call.id == call_id)) == (
        CallState.queued
    )


async def test_someone_elses_call_is_not_found(client, add_active_senior, queued):
    await add_active_senior(OTHER_SENIOR)
    call_id = (await card(client)).json()["call_id"]
    r = await answer(client, call_id, {"declined": True}, token=OTHER_SENIOR)
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("token", "status", "reason"),
    [
        (MEDIC, 403, "not_allowed"),
        (CAREGIVER, 403, "not_allowed"),
        (DAS, 403, "not_allowed"),
        (NO_GRANT, 403, "not_registered"),
        (None, 401, "not_signed_in"),
    ],
)
async def test_only_a_senior_reads_a_card(client, queued, token, status, reason):
    r = await card(client, token)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})


@pytest.mark.parametrize(
    ("token", "status", "reason"),
    [
        (MEDIC, 404, "not_found"),
        (CAREGIVER, 404, "not_found"),
        (DAS, 404, "not_found"),
        (NO_GRANT, 403, "not_registered"),
        (None, 401, "not_signed_in"),
    ],
)
async def test_only_the_senior_answers_her_call(
    client, db, queued, token, status, reason
):
    call_id = (await card(client)).json()["call_id"]
    r = await answer(client, call_id, {"declined": True}, token=token)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
    assert await db.scalar(select(Call.state).where(Call.id == call_id)) == (
        CallState.queued
    )


async def test_a_canceled_call_is_wrong_state(client, db, queued):
    call_id = (await card(client)).json()["call_id"]
    campaign_id = await db.scalar(select(Campaign.id))
    ended = await client.post(
        f"/api/campaigns/{campaign_id}/end", headers=signed_in(DAS)
    )
    assert ended.status_code == 200
    r = await answer(client, call_id, {"declined": True})
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})


async def test_the_card_skips_a_dialed_call(client, db, queued):
    await db.execute(update(Call).values(dialed_at=datetime.now(UTC)))
    await db.commit()
    assert (await card(client)).status_code == 204


async def test_answering_a_dialed_call_is_wrong_state(client, db, queued):
    call_id = (await card(client)).json()["call_id"]
    await db.execute(update(Call).values(dialed_at=datetime.now(UTC)))
    await db.commit()
    r = await answer(client, call_id, {"declined": True})
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})
    assert (await db.scalar(select(Call.state))) is CallState.queued


async def test_a_senior_no_longer_active_has_no_card_and_cannot_answer(
    client, db, queued
):
    call_id = (await card(client)).json()["call_id"]
    await db.execute(
        update(Senior)
        .where(Senior.id == queued.id)
        .values(enrollment_state=EnrollmentState.withdrawn)
    )
    await db.commit()
    assert (await card(client)).status_code == 204
    r = await answer(client, call_id, {"declined": True})
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})


async def test_the_card_shows_a_welcome_call_with_the_consent_text(
    client, db, add_active_senior
):
    senior = await add_active_senior(SENIOR)
    await db.execute(
        update(Senior)
        .where(Senior.id == senior.id)
        .values(enrollment_state=EnrollmentState.accepted)
    )
    db.add(
        Call(
            senior_id=senior.id,
            trigger=CallTrigger.welcome,
            starting_severity=Severity.green,
            due_at=datetime.now(UTC),
        )
    )
    await db.commit()
    r = await card(client)
    assert r.status_code == 200
    body = r.json()
    assert (body["trigger"], body["campaign_kind"], body["text_version"]) == (
        "welcome",
        None,
        "v1-app",
    )
    assert body["consent_text"].endswith("Sunteți de acord?")


async def test_no_mock_in_production(client, db, queued, monkeypatch):  # Q10
    call_id = (await card(client)).json()[
        "call_id"
    ]  # a real call, read before the gate
    monkeypatch.setattr(
        "app.calls.mock.get_settings",
        lambda: SimpleNamespace(app_env=AppEnv.production),
    )
    assert (await card(client)).status_code == 404
    r = await answer(client, call_id, {"declined": True})
    assert (r.status_code, r.json()) == (404, {"detail": {"reason": "not_found"}})
    state = await db.scalar(select(Call.state).where(Call.id == call_id))
    assert state == CallState.queued


@pytest.mark.parametrize("trigger", [t for t in CallTrigger if t not in mock.REQUIRES])
async def test_only_campaign_and_welcome_calls_are_answered(
    client, db, add_active_senior, trigger
):
    senior = await add_active_senior(SENIOR)
    call = Call(
        senior_id=senior.id,
        trigger=trigger,
        starting_severity=Severity.green,
        due_at=datetime.now(UTC),
    )
    db.add(call)
    await db.commit()
    r = await answer(client, call.id, {"declined": True})
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})
    assert await db.scalar(select(Call.state).where(Call.id == call.id)) == (
        CallState.queued
    )


@pytest.fixture
async def welcome_card(client, db, add_user, add_senior):
    """A submitted senior with her own number, accepted by DAS through the API; returns
    the card her app reads (Q11)."""
    await add_user(DAS, Role.das)
    senior = await add_senior(
        WELCOMED,
        enrollment_state=EnrollmentState.submitted,
        street="Str. Daliei",
        street_number="1",
    )
    herself = await add_user(WELCOMED)
    db.add(Grant(user_id=herself.id, role=Role.senior, senior_id=senior.id))
    await db.commit()
    r = await client.post(f"/api/seniors/{senior.id}/accept", headers=signed_in(DAS))
    assert r.status_code == 200
    return (await card(client, WELCOMED)).json()


async def welcomed(client, db):
    """The `welcome_card` senior, as DAS reads her."""
    senior_id = await db.scalar(select(Senior.id))
    r = await client.get(f"/api/seniors/{senior_id}", headers=signed_in(DAS))
    return r.json()


async def test_the_welcome_card_and_consent(client, db, welcome_card):
    assert (
        welcome_card["trigger"],
        welcome_card["text_version"],
        welcome_card["consent_text"],
    ) == ("welcome", "v1-app", CARD_CONSENT_TEXT)
    r = await answer(client, welcome_card["call_id"], {"consent": True}, WELCOMED)
    assert r.status_code == 204
    row = await welcomed(client, db)
    assert (row["enrollment_state"], row["code"]) == ("active", "green")
    assert row["reason"] == "Consimțământ dat"
    consent = (
        await db.execute(
            select(
                Consent.decision, Consent.method, Consent.text_version, Consent.call_id
            )
        )
    ).one()
    assert tuple(consent) == (
        "given",
        "app",
        CARD_CONSENT_VERSION,
        uuid.UUID(welcome_card["call_id"]),
    )
    assert (await card(client, WELCOMED)).status_code == 204
    ended = (
        await db.execute(
            select(Call.state, Call.welcome_outcome, Call.ended_at).where(
                Call.id == welcome_card["call_id"]
            )
        )
    ).one()
    assert (ended.state, ended.welcome_outcome, ended.ended_at is not None) == (
        CallState.completed,
        WelcomeOutcome.confirmed,
        True,
    )
    t = (
        await client.get(
            f"/api/calls/{welcome_card['call_id']}/transcript", headers=signed_in(DAS)
        )
    ).json()
    assert [(turn["speaker"], turn["content"]) for turn in t["turns"]] == [
        ("system", "Apel simulat din aplicație, fără linie telefonică."),
        ("agent", CARD_CONSENT_TEXT),
        ("senior", "Da"),
        (
            "agent",
            "Vă mulțumim. Nu vă vom cere niciodată bani sau date. O zi bună!",
        ),
    ]


async def test_welcome_no_refuses(client, db, welcome_card):
    r = await answer(client, welcome_card["call_id"], {"consent": False}, WELCOMED)
    assert r.status_code == 204
    row = await welcomed(client, db)
    assert (row["enrollment_state"], row["code"]) == ("refused", None)
    consent = (
        await db.execute(select(Consent.decision, Consent.method, Consent.text_version))
    ).one()
    assert tuple(consent) == ("refused", "app", "v1-app")
    t = (
        await client.get(
            f"/api/calls/{welcome_card['call_id']}/transcript", headers=signed_in(DAS)
        )
    ).json()
    assert [(turn["speaker"], turn["content"]) for turn in t["turns"]][2:] == [
        ("senior", "Nu"),
        ("agent", "Am înțeles. Nu vă vom mai suna. O zi bună!"),
    ]


async def test_welcome_needs_a_consent_answer(client, db, welcome_card):
    r = await answer(client, welcome_card["call_id"], {"declined": True}, WELCOMED)
    assert (r.status_code, r.json()) == (
        422,
        {"detail": {"reason": "incomplete", "missing": ["consent"]}},
    )
    assert (await welcomed(client, db))["enrollment_state"] == "accepted"


async def nothing_written(client, db, welcome_card, state):
    """The call is still `queued`, with no transcript or consent, and the senior is
    still in `state`."""
    call_id = welcome_card["call_id"]
    assert await db.scalar(select(Call.state).where(Call.id == call_id)) == (
        CallState.queued
    )
    assert await db.scalar(select(func.count()).select_from(Consent)) == 0
    t = (
        await client.get(f"/api/calls/{call_id}/transcript", headers=signed_in(DAS))
    ).json()
    assert t["turns"] == []
    assert (await welcomed(client, db))["enrollment_state"] == state


@pytest.mark.parametrize("state", [EnrollmentState.active, EnrollmentState.refused])
async def test_a_senior_no_longer_accepted_cannot_answer_the_welcome(
    client, db, welcome_card, state
):
    await db.execute(update(Senior).values(enrollment_state=state))
    await db.commit()
    r = await answer(client, welcome_card["call_id"], {"consent": True}, WELCOMED)
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})
    await nothing_written(client, db, welcome_card, state.name)


async def test_a_move_between_the_check_and_the_answer_writes_nothing(
    client, db, welcome_card, monkeypatch
):
    # The senior leaves `accepted` after the call row was read: conclude_welcome's guarded
    # update finds nobody and the answer is refused with nothing written (design §5).
    concluding = mock.conclude_welcome

    async def after_a_withdrawal(*args, **kwargs):
        await db.execute(
            update(Senior).values(enrollment_state=EnrollmentState.withdrawn)
        )
        await db.commit()
        return await concluding(*args, **kwargs)

    monkeypatch.setattr("app.calls.mock.conclude_welcome", after_a_withdrawal)
    r = await answer(client, welcome_card["call_id"], {"consent": True}, WELCOMED)
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})
    await nothing_written(client, db, welcome_card, "withdrawn")
