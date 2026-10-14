import os
from enum import StrEnum
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    # ConversationRelay's voice for ro-RO; which one sounds right is spike S1.
    twilio_tts_provider: str = "Google"
    twilio_voice: str = "ro-RO-Wavenet-A"
    # S3-compatible storage bucket (Railway storage for avatars, logs, blob data)
    s3_bucket_name: str = Field(
        "", validation_alias=AliasChoices("s3_bucket_name", "aws_bucket_name")
    )
    s3_endpoint: str = Field(
        "", validation_alias=AliasChoices("s3_endpoint", "aws_endpoint_url")
    )
    s3_access_key_id: str = Field(
        "", validation_alias=AliasChoices("s3_access_key_id", "aws_access_key_id")
    )
    s3_secret_access_key: str = Field(
        "",
        validation_alias=AliasChoices("s3_secret_access_key", "aws_secret_access_key"),
    )
    s3_region: str = Field(
        "ams",
        validation_alias=AliasChoices("s3_region", "aws_default_region", "aws_region"),
    )

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
    database lock (G9) and could dial staging's queue with the tunnel's address.
    """
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
