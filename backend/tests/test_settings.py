import pytest

from app.core.settings import Settings, check_environment, is_local_db


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


def test_s3_storage_settings():
    s_default = Settings(database_url=LOCAL, _env_file=None)
    assert s_default.s3_bucket_name == ""
    assert s_default.s3_endpoint == ""
    assert s_default.s3_region == "ams"

    s_custom = Settings(
        database_url=LOCAL,
        _env_file=None,
        s3_bucket_name="my-bucket",
        s3_endpoint="https://storage.ams.railway.app",
        s3_access_key_id="test-key",
        s3_secret_access_key="test-secret",
        s3_region="ams",
    )
    assert s_custom.s3_bucket_name == "my-bucket"
    assert s_custom.s3_endpoint == "https://storage.ams.railway.app"
    assert s_custom.s3_access_key_id == "test-key"
    assert s_custom.s3_secret_access_key == "test-secret"
    assert s_custom.s3_region == "ams"


def test_s3_aws_aliases(monkeypatch):
    monkeypatch.setenv("AWS_ENDPOINT_URL", "https://t3.storageapi.dev")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "aws-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    s = Settings(database_url=LOCAL, _env_file=None)
    assert s.s3_endpoint == "https://t3.storageapi.dev"
    assert s.s3_access_key_id == "aws-key"
    assert s.s3_secret_access_key == "aws-secret"
    assert s.s3_region == "eu-central-1"
