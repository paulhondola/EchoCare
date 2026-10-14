"""S3-compatible object storage service (app.core.storage).

Provides asynchronous object storage methods using boto3 and asyncio.to_thread
for non-blocking I/O against Railway's European S3 bucket or local MinIO.
"""

import asyncio
from functools import lru_cache
from typing import Any, BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.settings import Settings, get_settings


class StorageError(Exception):
    """Base exception for storage errors."""


class StorageNotConfiguredError(StorageError):
    """Raised when an operation is attempted without configured storage credentials/bucket."""


class StorageService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bucket_name = settings.s3_bucket_name

    @property
    def is_configured(self) -> bool:
        return bool(self._bucket_name)

    def _get_client(self) -> Any:
        if not self.is_configured:
            raise StorageNotConfiguredError(
                "S3 storage is not configured (missing bucket name)"
            )

        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": self._settings.s3_region or "ams",
            "config": Config(signature_version="s3v4"),
        }
        if self._settings.s3_endpoint:
            kwargs["endpoint_url"] = self._settings.s3_endpoint
        if self._settings.s3_access_key_id:
            kwargs["aws_access_key_id"] = self._settings.s3_access_key_id
        if self._settings.s3_secret_access_key:
            kwargs["aws_secret_access_key"] = self._settings.s3_secret_access_key

        return boto3.client(**kwargs)

    async def check_health(self) -> bool:
        """Check if S3 storage is configured and reachable."""
        if not self.is_configured:
            return False

        def _check() -> bool:
            try:
                client = self._get_client()
                client.head_bucket(Bucket=self._bucket_name)
                return True
            except ClientError, BotoCoreError, OSError:
                return False

        return await asyncio.to_thread(_check)

    async def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes or file-like object to S3."""
        if not self.is_configured:
            raise StorageNotConfiguredError("S3 storage is not configured")

        def _upload() -> str:
            client = self._get_client()
            client.put_object(
                Bucket=self._bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            return key

        return await asyncio.to_thread(_upload)

    async def download(self, key: str) -> bytes:
        """Download file content from S3 as bytes."""
        if not self.is_configured:
            raise StorageNotConfiguredError("S3 storage is not configured")

        def _download() -> bytes:
            client = self._get_client()
            try:
                response = client.get_object(Bucket=self._bucket_name, Key=key)
                return response["Body"].read()
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in ("NoSuchKey", "404"):
                    raise FileNotFoundError(
                        f"Key '{key}' not found in bucket '{self._bucket_name}'"
                    ) from e
                raise StorageError(f"Failed to download '{key}': {e}") from e

        return await asyncio.to_thread(_download)

    async def delete(self, key: str) -> bool:
        """Delete an object from S3."""
        if not self.is_configured:
            raise StorageNotConfiguredError("S3 storage is not configured")

        def _delete() -> bool:
            client = self._get_client()
            try:
                client.delete_object(Bucket=self._bucket_name, Key=key)
                return True
            except ClientError as e:
                raise StorageError(f"Failed to delete '{key}': {e}") from e

        return await asyncio.to_thread(_delete)

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "get_object",
    ) -> str:
        """Generate a presigned URL for downloading or uploading."""
        if not self.is_configured:
            raise StorageNotConfiguredError("S3 storage is not configured")

        def _presign() -> str:
            client = self._get_client()
            return client.generate_presigned_url(
                ClientMethod=method,
                Params={"Bucket": self._bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )

        return await asyncio.to_thread(_presign)


@lru_cache
def get_storage() -> StorageService:
    return StorageService(get_settings())
