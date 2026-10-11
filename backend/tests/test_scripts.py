import pytest

from scripts.grant_das import grant_das


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
