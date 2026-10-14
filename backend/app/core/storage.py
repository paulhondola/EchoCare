"""S3-compatible object storage service (app.core.storage).

Provides asynchronous object storage methods against Railway's European S3 bucket or
local MinIO. boto3 blocks, so its calls run on a small thread pool of their own: a slow
bucket can't starve asyncio's default executor, which also resolves DNS for asyncpg and
httpx.
"""

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property, lru_cache
from typing import Any, BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.settings import Settings, get_settings

log = logging.getLogger("sentinela.storage")

# SigV4 refuses presigned URLs that live longer than a week.
MAX_PRESIGN_SECONDS = 7 * 24 * 3600


class StorageError(Exception):
    """Base exception for storage errors."""


class StorageNotConfiguredError(StorageError):
    """Raised when an operation is attempted without configured storage credentials/bucket."""


def _check_expiry(expires_in: int) -> None:
    if not 1 <= expires_in <= MAX_PRESIGN_SECONDS:
        raise ValueError(
            f"expires_in must be 1..{MAX_PRESIGN_SECONDS} seconds, got {expires_in}"
        )


class StorageService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bucket_name = settings.s3_bucket_name
        # ponytail: 4 threads cap concurrent S3 calls; raise it if uploads queue up.
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="s3")

    @property
    def is_configured(self) -> bool:
        return bool(self._bucket_name)

    def _new_client(self, endpoint: str) -> Any:
        # A Session of its own: boto3's default Session is shared and not thread-safe.
        # Timeouts and retries are bounded so a dead bucket fails in seconds, not minutes.
        return boto3.session.Session().client(
            "s3",
            region_name=self._settings.s3_region or "ams",
            endpoint_url=endpoint or None,
            aws_access_key_id=self._settings.s3_access_key_id or None,
            aws_secret_access_key=self._settings.s3_secret_access_key or None,
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    # Clients are thread-safe and keep their connection pool, so each is built once.
    # ponytail: no lock; two racing first calls may build a spare client, which is harmless.
    @cached_property
    def _client(self) -> Any:
        return self._new_client(self._settings.s3_endpoint)

    @cached_property
    def _presign_client(self) -> Any:
        # Browsers and phones open presigned URLs and can't reach Compose's minio:9000;
        # the host is part of the signature, so the URL must be built with the public one.
        public = self._settings.s3_public_endpoint
        return self._new_client(public) if public else self._client

    async def _run[T](self, what: str, call: Callable[[], T]) -> T:
        """Runs a blocking boto3 call on the storage pool; boto3's failures become StorageError."""
        if not self.is_configured:
            raise StorageNotConfiguredError("S3 storage is not configured")

        def guarded() -> T:
            try:
                return call()
            # ValueError: botocore's answer to an endpoint without http(s)://
            except (ClientError, BotoCoreError, ValueError) as e:
                raise StorageError(f"Failed to {what}: {e}") from e

        return await asyncio.get_running_loop().run_in_executor(self._executor, guarded)

    async def check_health(self) -> bool:
        """Check if S3 storage is configured and reachable."""
        if not self.is_configured:
            return False
        try:
            await self._run(
                "reach the bucket",
                lambda: self._client.head_bucket(Bucket=self._bucket_name),
            )
        except StorageError:
            log.warning("S3 health check failed", exc_info=True)
            return False
        return True

    async def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Upload raw bytes or file-like object to S3."""
        await self._run(
            f"upload '{key}'",
            lambda: self._client.put_object(
                Bucket=self._bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            ),
        )

    async def download(self, key: str) -> bytes:
        """Download file content from S3 as bytes."""

        def _download() -> bytes:
            try:
                response = self._client.get_object(Bucket=self._bucket_name, Key=key)
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("NoSuchKey", "404"):
                    raise FileNotFoundError(
                        f"Key '{key}' not found in bucket '{self._bucket_name}'"
                    ) from e
                raise
            return response["Body"].read()

        return await self._run(f"download '{key}'", _download)

    async def delete(self, key: str) -> None:
        """Delete an object from S3. A missing key succeeds too: S3's delete is idempotent."""
        await self._run(
            f"delete '{key}'",
            lambda: self._client.delete_object(Bucket=self._bucket_name, Key=key),
        )

    async def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned download URL, valid for expires_in seconds."""
        _check_expiry(expires_in)
        return await self._run(
            f"presign '{key}'",
            lambda: self._presign_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self._bucket_name, "Key": key},
                ExpiresIn=expires_in,
            ),
        )

    async def generate_presigned_post(
        self, key: str, content_type: str, max_bytes: int, expires_in: int = 3600
    ) -> dict[str, Any]:
        """Generate an upload form ({"url", "fields"}) for one key.

        S3 enforces the form's conditions: this Content-Type and 1..max_bytes bytes. A
        presigned PUT can limit neither, so uploads from browsers and phones use this.
        """
        _check_expiry(expires_in)
        return await self._run(
            f"presign upload '{key}'",
            lambda: self._presign_client.generate_presigned_post(
                Bucket=self._bucket_name,
                Key=key,
                Fields={"Content-Type": content_type},
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1, max_bytes],
                ],
                ExpiresIn=expires_in,
            ),
        )


@lru_cache
def get_storage() -> StorageService:
    return StorageService(get_settings())
