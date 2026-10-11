import pytest

from app.settings import Settings, check_environment, check_firebase, is_local_db


def test_railway_url_gets_asyncpg_driver():
    s = Settings(database_url="postgresql://u:p@postgres.railway.internal:5432/railway")
    assert (
        s.database_url
        == "postgresql+asyncpg://u:p@postgres.railway.internal:5432/railway"
    )


def test_local_hosts():
    assert is_local_db("postgresql+asyncpg://u:p@localhost:5432/sentinela")
    assert is_local_db("postgresql+asyncpg://u:p@db:5432/sentinela")
    assert not is_local_db(
        "postgresql+asyncpg://u:p@postgres.railway.internal:5432/railway"
    )
    assert not is_local_db(
        "postgresql+asyncpg://u:p@shuttle.proxy.rlwy.net:41234/railway"
    )


REMOTE = "postgresql://u:p@shuttle.proxy.rlwy.net:41234/railway"
LOCAL = "postgresql://sentinela:sentinela@localhost:5432/sentinela"


def check(monkeypatch, url, scheduler, deployment_id=None):
    if deployment_id:
        monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", deployment_id)
    else:
        monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    check_environment(Settings(database_url=url, scheduler_enabled=scheduler))


def test_laptop_scheduler_on_cloud_db_refuses(monkeypatch):
    with pytest.raises(SystemExit, match="shuttle.proxy.rlwy.net"):
        check(monkeypatch, REMOTE, scheduler=True)


def test_allowed_combinations(monkeypatch):
    check(monkeypatch, REMOTE, scheduler=False)  # debugging against staging
    check(monkeypatch, LOCAL, scheduler=True)  # everyday local development
    check(
        monkeypatch, REMOTE, scheduler=True, deployment_id="dep-1"
    )  # deployed on Railway


def test_firebase_key_required_on_railway(monkeypatch):
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "dep-1")
    # passed explicitly: a laptop's backend/.env may hold the key
    with pytest.raises(SystemExit, match="FIREBASE_SERVICE_ACCOUNT"):
        check_firebase(Settings(database_url=LOCAL, firebase_service_account=None))
    check_firebase(Settings(database_url=LOCAL, firebase_service_account="{}"))


def test_firebase_key_optional_on_a_laptop(monkeypatch):
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    check_firebase(Settings(database_url=LOCAL, firebase_service_account=None))
