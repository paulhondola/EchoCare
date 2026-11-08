import pytest
from pydantic import ValidationError

from app.core.settings import (
    AppEnv,
    Settings,
    check_environment,
    cors_origins,
    is_local_db,
)


def test_railway_url_gets_asyncpg_driver():
    s = Settings(database_url="postgresql://u:p@postgres.railway.internal:5432/railway")
    assert (
        s.database_url
        == "postgresql+asyncpg://u:p@postgres.railway.internal:5432/railway"
    )


def test_local_hosts():
    assert is_local_db("postgresql+asyncpg://u:p@localhost:5432/echocare")
    assert is_local_db("postgresql+asyncpg://u:p@db:5432/echocare")
    assert not is_local_db(
        "postgresql+asyncpg://u:p@postgres.railway.internal:5432/railway"
    )
    assert not is_local_db(
        "postgresql+asyncpg://u:p@shuttle.proxy.rlwy.net:41234/railway"
    )


REMOTE = "postgresql://u:p@shuttle.proxy.rlwy.net:41234/railway"
LOCAL = "postgresql://echocare:echocare@localhost:5432/echocare"


def check(monkeypatch, url, scheduler, deployment_id=None, app_env="staging"):
    if deployment_id:
        monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", deployment_id)
    else:
        monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    if app_env:
        monkeypatch.setenv("APP_ENV", app_env)
    else:
        monkeypatch.delenv("APP_ENV", raising=False)
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


def test_railway_without_app_env_refuses(monkeypatch):  # Q10
    with pytest.raises(SystemExit, match="APP_ENV"):
        check(monkeypatch, REMOTE, scheduler=True, deployment_id="dep-1", app_env=None)
    check(monkeypatch, REMOTE, scheduler=True, deployment_id="dep-1")  # APP_ENV set
    check(monkeypatch, LOCAL, scheduler=True, app_env=None)  # a laptop needs none


S3_VARS = (
    "S3_BUCKET_NAME",
    "S3_ENDPOINT",
    "S3_PUBLIC_ENDPOINT",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "S3_REGION",
)


def test_s3_storage_settings(monkeypatch):
    for name in S3_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-1")  # boto3's own; settings ignore it
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


def test_s3_settings_from_railway_env(monkeypatch):
    # The names railway.ts maps the bucket's variables to.
    env = {
        "S3_BUCKET_NAME": "bucket",
        "S3_ENDPOINT": "https://t3.storageapi.dev",
        "S3_PUBLIC_ENDPOINT": "https://public.example",
        "S3_ACCESS_KEY_ID": "key",
        "S3_SECRET_ACCESS_KEY": "secret",
        "S3_REGION": "auto",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    s = Settings(database_url=LOCAL, _env_file=None)
    assert {name: getattr(s, name.lower()) for name in env} == env


def test_allowlist_normalizes_and_drops_blanks():
    s = Settings(
        database_url="postgresql://x@localhost/x",
        dial_allowlist="0722 123 456, ,+40722000001,",
    )
    assert s.dial_allowlist == "+40722123456,+40722000001"


def test_allowlist_keeps_a_lone_star():
    s = Settings(database_url="postgresql://x@localhost/x", dial_allowlist=" * ")
    assert s.dial_allowlist == "*"


def test_allowlist_refuses_an_invalid_number():
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql://x@localhost/x", dial_allowlist="12")


def test_local_cors_allows_the_dev_server_under_both_names():
    # Real-SMS sign-in works only on 127.0.0.1 (dashboard/README.md), test numbers on either
    s = Settings(database_url=LOCAL, app_env=AppEnv.local, _env_file=None)
    assert sorted(cors_origins(s)) == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]


def test_cloud_cors_allows_only_allowed_origin():  # 01 §4, channel 3
    origin = "https://echocare-dashboard-staging.up.railway.app"
    s = Settings(
        database_url=REMOTE,
        app_env=AppEnv.staging,
        allowed_origin=origin,
        _env_file=None,
    )
    assert cors_origins(s) == [origin]


def test_the_agent_model_defaults_to_deepseek_v4_pro(monkeypatch):
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    s = Settings(database_url="postgresql+asyncpg://x/y", _env_file=None)
    assert s.agent_model == "deepseek-ai/DeepSeek-V4-Pro"
    assert s.deepinfra_api_key == ""
