from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models import Call, Grant, Incident, Role, Senior, User
from scripts import seed as seed_script
from scripts.grant_das import grant_das
from scripts.seed import SENIORS, seed

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


async def test_seed_reports_a_number_already_another_seniors(db, add_senior, capsys):
    other = await add_senior("+40700000150")
    user = User(phone_e164="+40700000005", display_name="Other")
    db.add(user)
    await db.flush()
    db.add(Grant(user_id=user.id, role=Role.senior, senior_id=other.id))
    await db.commit()

    assert await seed() == "seeded"
    assert "+40700000005 is already another senior's" in capsys.readouterr().err


async def test_seed_refuses_a_cloud_database(monkeypatch):
    cloud = SimpleNamespace(
        database_url="postgresql://u:p@postgres.railway.internal/db"
    )
    monkeypatch.setattr(seed_script, "get_settings", lambda: cloud)
    with pytest.raises(SystemExit, match="postgres.railway.internal"):
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
