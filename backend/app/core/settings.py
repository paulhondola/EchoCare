import os
from enum import StrEnum
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.phones import normalize

# Hosts a laptop may migrate or run a scheduler against: the host's Postgres and Compose's db.
LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "db"}


class AppEnv(StrEnum):
    local = "local"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: AppEnv = AppEnv.local
    database_url: str
    public_base_url: str = "http://localhost:8000"
    allowed_origin: str = "http://localhost:5173"
    scheduler_enabled: bool = True
    demo_mode: bool = True
    # Twilio (04 §4). Empty until a person creates the account; every callback is then
    # refused, since no signature can match (#15).
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    # The Voice API's host; an Ireland (IE1) account answers on its own, with its own
    # auth token.
    twilio_api_host: str = "api.twilio.com"
    # How many calls may be live at once, the trial account's limit (G9).
    max_live_calls: int = 3
    # Who the scheduler may dial: comma-joined E.164 numbers, `*` for everyone, empty for
    # nobody. Keeps a laptop or staging from ringing real seniors.
    dial_allowlist: str = ""
    # ConversationRelay's voice for ro-RO; which one sounds right is spike S1.
    twilio_tts_provider: str = "Google"
    twilio_voice: str = "ro-RO-Wavenet-A"
    # S3-compatible storage bucket (Railway storage for avatars, logs, blob data)
    s3_bucket_name: str = ""
    s3_endpoint: str = ""
    # The host in presigned URLs, for clients that can't reach s3_endpoint (Compose's
    # minio:9000); empty means s3_endpoint.
    s3_public_endpoint: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "ams"

    @field_validator("dial_allowlist")
    @classmethod
    def normalize_allowlist(cls, raw: str) -> str:
        entries = [e.strip() for e in raw.split(",") if e.strip()]
        return ",".join(e if e == "*" else normalize(e) for e in entries)

    @field_validator("database_url")
    @classmethod
    def use_asyncpg(cls, url: str) -> str:
        # Railway's DATABASE_URL is postgresql://; SQLAlchemy's async engine needs the asyncpg driver.
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url.removeprefix(prefix)
        return url


def db_host(url: str) -> str:
    return urlsplit(url).hostname or ""


def is_local_db(url: str) -> bool:
    return db_host(url) in LOCAL_DB_HOSTS


def on_railway() -> bool:
    # A deployment id exists only inside a running Railway deployment; `railway run` on a
    # laptop copies the service's variables, which can include RAILWAY_ENVIRONMENT_NAME.
    return "RAILWAY_DEPLOYMENT_ID" in os.environ


def check_environment(settings: Settings) -> None:
    """Stop a laptop's API from competing with a cloud environment's scheduler (ADR-001).

    A local API pointed at staging's database would race staging's scheduler for the
    database lock (G9) and could dial staging's queue with a local address.

    Also stop a Railway deployment that lost `APP_ENV`: `app_env` would default to
    `local`, and the mock call's production gate (Q10) would open.
    """
    if on_railway() and "APP_ENV" not in os.environ:
        raise SystemExit(
            "Refusing to start: APP_ENV is not set on this Railway deployment, so it "
            "would run as local and the mock call (Q10) would not be gated. Set "
            "APP_ENV to staging or production."
        )
    if (
        settings.scheduler_enabled
        and not is_local_db(settings.database_url)
        and not on_railway()
    ):
        raise SystemExit(
            f"Refusing to start: the scheduler would dial from this machine against "
            f"{db_host(settings.database_url)}. Set SCHEDULER_ENABLED=false to debug "
            "against a cloud database."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
