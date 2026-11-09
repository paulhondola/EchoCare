import uuid
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import exists, func, select

from app.core.settings import get_settings
from app.memory.service import ENDED_ANSWERED, summary_input
from app.memory.writer import citation_errors
from app.models import (
    Call,
    Campaign,
    EnrollmentState,
    Grant,
    Incident,
    Role,
    Senior,
    SummaryVersion,
    User,
)
from app.seniors.schemas import SummaryContent
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.models import WELLBEING
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


async def all_versions(db) -> dict[uuid.UUID, list[SummaryVersion]]:
    """Each senior's versions, oldest first."""
    chains: dict[uuid.UUID, list[SummaryVersion]] = {}
    for v in await db.scalars(
        select(SummaryVersion).order_by(SummaryVersion.created_at)
    ):
        chains.setdefault(v.senior_id, []).append(v)
    return chains


def test_a_second_seniors_first_version_starts_its_own_chain():
    """Nicolae refused on the welcome call, so he has no version of his own; his first
    must not chain to another senior's latest (design §4)."""
    h = seed_script.build(datetime.now(UTC), fake_users())
    assert h.summaries  # other seniors' versions come first
    welcome = next(c for c in h.calls if c.senior_id == h.seniors["nicolae"].id)
    h.summarize(
        "nicolae",
        welcome,
        follow_ups=[],
        how_to_talk=[],
        trends=[],
        narrative="Domnul Nicolae nu vrea să fie sunat.",
    )
    assert h.summaries[-1].previous_id is None
    assert h.summaries[-1].id == seed_script.seed_id("summary", "nicolae", "1")


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
    # Every senior's versions form a chain of their own (design §4).
    for chain in (await all_versions(db)).values():
        assert chain[0].previous_id is None
        assert [v.previous_id for v in chain[1:]] == [v.id for v in chain[:-1]]


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
    """Every seeded version passes the writer's own check, on the input the live writer
    builds: the current call's turns, and only answers for earlier calls (design §4)."""
    await seed(reset=True)
    for senior, chain in (await all_versions(db)).items():
        previous = None
        for i, v in enumerate(chain):
            _, _, data = await summary_input(db, v.call_id)
            data = replace(data, previous=previous)
            content = SummaryContent.model_validate(v.content)
            assert citation_errors(data, content) == [], (senior, i)
            previous = content


async def test_every_answered_wellbeing_call_has_a_version(db):
    """Else the briefing skips it, and on staging with a key due_calls would send a
    seeded call to the paid model (staging seed design §4.5)."""
    await seed(reset=True)
    missing = await db.scalars(
        select(Call.id)
        .join(Senior, Senior.id == Call.senior_id)
        .where(
            seed_script.SEEDED,
            Senior.enrollment_state == EnrollmentState.active,
            Call.trigger.in_(WELLBEING),
            Call.state.in_(ENDED_ANSWERED),
            ~exists().where(SummaryVersion.call_id == Call.id),
        )
    )
    assert list(missing) == []


async def test_latest_trends_show_every_direction(db):
    await seed(reset=True)
    directions = set()
    for chain in (await all_versions(db)).values():
        latest = SummaryContent.model_validate(chain[-1].content)
        directions |= {t.direction for t in latest.trends}
    assert directions >= {"worse", "better", "steady"}


async def test_every_active_seeded_senior_has_a_briefing(db):
    await seed(reset=True)
    chains = await all_versions(db)
    active = list(
        await db.scalars(
            select(Senior.id).where(
                seed_script.SEEDED, Senior.enrollment_state == EnrollmentState.active
            )
        )
    )
    assert active and all(s in chains for s in active)


async def test_no_campaign_call_predates_its_campaign(db):
    """A campaign's progress counts its calls (04 §2): calls from weeks before the running
    campaign belong to an earlier one, or the card counts seniors it never called."""
    await seed(reset=True)
    early = await db.scalars(
        select(Call.id)
        .join(Campaign, Campaign.id == Call.campaign_id)
        .where(Call.due_at < Campaign.started_at)
    )
    assert list(early) == []


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


async def test_seed_refuses_a_cloud_database_that_dials_everyone(monkeypatch):
    """Staging seed design §2: the seeded numbers are made up, in a premium-rate range;
    with DIAL_ALLOWLIST=* the first campaign would ring them."""
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql://u@postgres.railway.internal/r")
    monkeypatch.setattr(s, "app_env", "staging")
    monkeypatch.setattr(s, "dial_allowlist", "*")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "d-1")
    with pytest.raises(SystemExit, match="DIAL_ALLOWLIST"):
        await seed(confirm="staging")


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
