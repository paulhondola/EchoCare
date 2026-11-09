import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select

from app.core.settings import get_settings
from app.memory.writer import CallFacts, SummaryInput, citation_errors
from app.models import (
    Answer,
    Call,
    CallTurn,
    Grant,
    Incident,
    Role,
    Senior,
    SummaryVersion,
    User,
)
from app.seniors.schemas import SummaryContent
from app.status.engine import BUCHAREST, Severity
from app.voice.calls import CallState
from scripts import seed as seed_script
from scripts.grant_das import grant_das
from scripts.place_call import place_call
from scripts.seed import SENIORS, seed

DEMO = "Eugenia Tudor"

DAS = {"Authorization": "Bearer +40700000001"}


async def count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def test_seed_fills_the_dashboard_once(db, client):
    assert await seed() == "seeded"
    assert await seed() == "already seeded"

    r = await client.get("/api/incidents?status=open,in_progress,resolved", headers=DAS)
    incidents = r.json()
    assert sorted(i["status"] for i in incidents) == (
        ["in_progress"] * 4 + ["open"] * 4 + ["resolved"] * 6
    )
    for incident in incidents:
        r = await client.get(f"/api/incidents/{incident['id']}", headers=DAS)
        assert r.json()["calls"], incident["senior_full_name"]
        assert all(c["relation"] for c in r.json()["caregivers"])
    r = await client.get("/api/enrollments", headers=DAS)
    assert [s["full_name"] for s in r.json()] == ["Constantin Barbu", "Elisabeta Nagy"]
    # Every senior past draft, as DAS sees them (auth-layer §3.6).
    r = await client.get("/api/seniors", headers=DAS)
    assert len(r.json()) == len(SENIORS) - 1


async def test_seed_reset_replaces_only_its_own_rows(db, add_senior):
    other = await add_senior("+40700000150", name="Not Seeded")
    assert await seed() == "seeded"
    medic = await db.scalar(select(User).where(User.phone_e164 == "+40700000002"))
    # Registered through the API by the seeded medic, who must outlive the reset.
    theirs = await add_senior("+40700000151", name="Theirs", medic=medic)
    calls, users = await count(db, Call), await count(db, User)

    assert await seed(reset=True) == "reseeded"
    assert await count(db, Call) == calls
    assert await count(db, User) == users
    assert await count(db, Incident) == 14
    # A query, not db.get, which would answer from the session's identity map.
    kept = select(func.count()).where(Senior.id.in_([other.id, theirs.id]))
    assert await db.scalar(kept) == 2


async def demo_versions(db) -> list[SummaryVersion]:
    rows = await db.scalars(
        select(SummaryVersion)
        .join(Senior, Senior.id == SummaryVersion.senior_id)
        .where(Senior.full_name == DEMO)
        .order_by(SummaryVersion.created_at)
    )
    return list(rows)


async def test_seed_writes_a_chain_of_versions(db):
    await seed(reset=True)
    versions = await demo_versions(db)
    assert len(versions) == 6
    assert versions[0].previous_id is None
    assert [v.previous_id for v in versions[1:]] == [v.id for v in versions[:-1]]
    assert len({v.call_id for v in versions}) == 6
    latest = SummaryContent.model_validate(versions[-1].content)
    assert "caloriferul" in latest.follow_ups[0].topic
    assert [t.direction for t in latest.trends] == ["worse"]
    c4, c6 = versions[3].call_id, versions[5].call_id
    assert [e.call_id for e in latest.trends[0].evidence] == [c4, c6]
    assert latest.follow_ups[0].call_id == c6


async def test_demo_calls_match_their_answers(db):
    """03 §3: a wrong day, or no heat on a cold campaign, is yellow, with that reason."""
    await seed(reset=True)
    versions = await demo_versions(db)
    for v in (versions[3], versions[5]):
        call = await db.get(Call, v.call_id)
        assert call.final_severity is Severity.yellow
        assert "Se simte bine" not in call.reason
        assert "nu știe ce zi este" in call.reason.lower()


async def test_seeded_citations_are_real(db):
    await seed(reset=True)
    versions = await demo_versions(db)
    assert len(versions) == 6
    facts: list[CallFacts] = []
    for v in versions:
        call = await db.get(Call, v.call_id)
        turns = await db.execute(
            select(CallTurn.speaker, CallTurn.content)
            .where(CallTurn.call_id == call.id)
            .order_by(CallTurn.position)
        )
        answers = await db.execute(
            select(Answer.field, Answer.value, Answer.clear, Answer.quote).where(
                Answer.call_id == call.id
            )
        )
        facts.append(
            CallFacts(
                id=call.id,
                trigger=call.trigger.value,
                campaign_kind=None,
                date=call.due_at.astimezone(BUCHAREST).date(),
                state=call.state.value,
                final_severity=call.final_severity and call.final_severity.name,
                final_certainty=call.final_certainty and call.final_certainty.name,
                reason=call.reason,
                turns=[(sp.value, text) for sp, text in turns],
                answers=[tuple(a) for a in answers],
            )
        )
    previous = None
    for i, v in enumerate(versions):
        content = SummaryContent.model_validate(v.content)
        data = SummaryInput(
            previous=previous, call=facts[i], earlier=list(reversed(facts[:i]))
        )
        assert citation_errors(data, content) == [], i
        previous = content


async def test_seed_reset_is_repeatable(db):
    await seed(reset=True)
    first = len(await demo_versions(db))
    await seed(reset=True)
    assert len(await demo_versions(db)) == first == 6


async def test_seed_reports_a_number_already_another_seniors(db, add_senior, capsys):
    other = await add_senior("+40700000150")
    user = User(phone_e164="+40700000005", display_name="Other")
    db.add(user)
    await db.flush()
    db.add(Grant(user_id=user.id, role=Role.senior, senior_id=other.id))
    await db.commit()

    assert await seed() == "seeded"
    assert "+40700000005 is already another senior's" in capsys.readouterr().err


def fake_users() -> dict[str, uuid.UUID]:
    """What add_people returns, with no database: each number's user id."""
    return {p.phone: uuid.uuid4() for p in seed_script.people()}


def test_cloud_build_grants_no_das_and_lapses_the_campaign():
    """Staging design §4.2, §4.3: only the team holds das there, and a campaign the team
    starts is not answered by the seeded one."""
    now = datetime.now(UTC)
    h = seed_script.build(now, fake_users(), cloud=True)
    assert Role.das not in {g["role"] for g in h.grants}
    assert Role.medic in {g["role"] for g in h.grants}
    assert h.campaign.warning_until < now


def test_local_build_keeps_das_and_a_running_campaign():
    now = datetime.now(UTC)
    h = seed_script.build(now, fake_users())
    assert Role.das in {g["role"] for g in h.grants}
    assert h.campaign.warning_until > now


async def test_seed_refuses_a_cloud_database_from_a_laptop(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql://u@postgres.railway.internal/r")
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    with pytest.raises(SystemExit, match="inside the api container"):
        await seed(confirm="staging")


async def test_seed_refuses_production_even_confirmed(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql://u@postgres.railway.internal/r")
    monkeypatch.setattr(s, "app_env", "production")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "d-1")
    with pytest.raises(SystemExit, match="production"):
        await seed(confirm="production")


async def test_seed_on_staging_needs_its_name(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql://u@postgres.railway.internal/r")
    monkeypatch.setattr(s, "app_env", "staging")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "d-1")
    with pytest.raises(SystemExit, match="--confirm staging"):
        await seed()


async def test_grant_das_twice(db):
    assert await grant_das("Ana Pop", "0700 000 001") == "granted"
    assert await grant_das("Ana Pop", "+40700000001") == "already granted"


async def test_grant_das_refuses_a_landline(db):
    assert await grant_das("Ana Pop", "0256 123 456") == "invalid"


@pytest.mark.parametrize("name", ["   ", "x" * 121])  # as POST /staff (§3.4)
async def test_grant_das_refuses_a_blank_or_long_name(db, name):
    assert await grant_das(name, "+40700000001") == "invalid"


def test_dev_token_reads_key_from_env(monkeypatch):
    from scripts.dev_token import get_web_api_key

    monkeypatch.setenv("FIREBASE_WEB_API_KEY", "test-key-123")
    assert get_web_api_key() == "test-key-123"


def test_dev_token_reads_key_from_env_file(tmp_path, monkeypatch):
    from scripts.dev_token import get_web_api_key

    monkeypatch.delenv("FIREBASE_WEB_API_KEY", raising=False)
    monkeypatch.delenv("VITE_FIREBASE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("FIREBASE_WEB_API_KEY=test-file-key\n")
    assert get_web_api_key(env_path=env_file) == "test-file-key"


def test_dev_token_errors_when_key_missing(tmp_path, monkeypatch):
    from scripts.dev_token import get_web_api_key

    monkeypatch.delenv("FIREBASE_WEB_API_KEY", raising=False)
    monkeypatch.delenv("VITE_FIREBASE_API_KEY", raising=False)
    empty_env = tmp_path / ".env"
    empty_env.write_text("OTHER_VAR=123\n")
    with pytest.raises(SystemExit, match="FIREBASE_WEB_API_KEY"):
        get_web_api_key(env_path=empty_env)


async def test_place_call_stamps_dialed_at_and_follows_the_allowlist(
    db, add_senior, monkeypatch
):
    s = get_settings()
    monkeypatch.setattr(s, "twilio_account_sid", "AC1")
    monkeypatch.setattr(s, "twilio_auth_token", "token")
    monkeypatch.setattr(s, "twilio_from_number", "+40700000999")
    monkeypatch.setattr(s, "dial_allowlist", "")
    await add_senior("+40700000101")

    placed, message = await place_call("0700000101")
    assert not placed and "DIAL_ALLOWLIST" in message
    assert await count(db, Call) == 0

    async def times_out(*_):
        raise httpx.ReadTimeout("x")

    monkeypatch.setattr(s, "dial_allowlist", "+40700000101")
    monkeypatch.setattr("scripts.place_call.dial", times_out)
    placed, message = await place_call("0700000101")
    assert not placed and message.startswith("outcome unknown")
    call = await db.scalar(select(Call))
    assert call.state is CallState.queued and call.dialed_at is not None
