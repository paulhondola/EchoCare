import boto3
import pytest
from moto import mock_aws

from app.core.settings import Settings
from app.core.storage import StorageNotConfiguredError, StorageService


@pytest.fixture
def s3_settings():
    return Settings(
        database_url="postgresql://sentinela:sentinela@localhost:5432/sentinela_test",
        _env_file=None,
        s3_bucket_name="sentinela-test",
        s3_endpoint="https://s3.eu-west-1.amazonaws.com",
        s3_access_key_id="test-key",
        s3_secret_access_key="test-secret",
        s3_region="eu-west-1",
    )


@pytest.fixture
def unconfigured_settings():
    return Settings(
        database_url="postgresql://sentinela:sentinela@localhost:5432/sentinela_test",
        _env_file=None,
        s3_bucket_name="",
    )


@pytest.mark.asyncio
async def test_unconfigured_storage(unconfigured_settings):
    storage = StorageService(unconfigured_settings)
    assert not storage.is_configured
    assert await storage.check_health() is False

    with pytest.raises(StorageNotConfiguredError):
        await storage.upload("test.txt", b"hello")

    with pytest.raises(StorageNotConfiguredError):
        await storage.download("test.txt")

    with pytest.raises(StorageNotConfiguredError):
        await storage.delete("test.txt")

    with pytest.raises(StorageNotConfiguredError):
        await storage.generate_presigned_url("test.txt")


@pytest.mark.asyncio
async def test_storage_crud(s3_settings):
    with mock_aws():
        # Setup mock bucket using synchronous boto3
        s3 = boto3.client(
            "s3",
            region_name=s3_settings.s3_region,
            aws_access_key_id=s3_settings.s3_access_key_id,
            aws_secret_access_key=s3_settings.s3_secret_access_key,
        )
        s3.create_bucket(
            Bucket=s3_settings.s3_bucket_name,
            CreateBucketConfiguration={"LocationConstraint": s3_settings.s3_region},
        )

        storage = StorageService(s3_settings)
        assert storage.is_configured
        assert await storage.check_health() is True

        # Test Upload
        key = "avatars/senior-1.png"
        content = b"\x89PNG\r\n\x1a\nfakeimagecontent"
        uploaded_key = await storage.upload(key, content, content_type="image/png")
        assert uploaded_key == key

        # Test Download
        downloaded = await storage.download(key)
        assert downloaded == content

        # Test Presigned URL for GET and PUT
        url_get = await storage.generate_presigned_url(key, expires_in=1800)
        assert "avatars/senior-1.png" in url_get

        url_put = await storage.generate_presigned_url(
            key, expires_in=1800, method="put_object"
        )
        assert "avatars/senior-1.png" in url_put

        # Test Delete
        assert await storage.delete(key) is True

        # Test Download non-existent file
        with pytest.raises(FileNotFoundError):
            await storage.download(key)


@pytest.mark.asyncio
async def test_storage_binary_io(s3_settings):
    import io

    with mock_aws():
        s3 = boto3.client("s3", region_name=s3_settings.s3_region)
        s3.create_bucket(
            Bucket=s3_settings.s3_bucket_name,
            CreateBucketConfiguration={"LocationConstraint": s3_settings.s3_region},
        )
        storage = StorageService(s3_settings)
        data = io.BytesIO(b"binary-stream-data")
        await storage.upload("stream.bin", data)

        downloaded = await storage.download("stream.bin")
        assert downloaded == b"binary-stream-data"


def test_get_storage_provider():
    from app.core.storage import get_storage

    s1 = get_storage()
    s2 = get_storage()
    assert s1 is s2
