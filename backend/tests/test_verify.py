import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from firebase_admin import auth as fb

from app import auth

TOKEN = HTTPAuthorizationCredentials(scheme="Bearer", credentials="a.b.c")


def refusal(e: pytest.ExceptionInfo[HTTPException]) -> tuple[int, str]:
    return e.value.status_code, e.value.detail["reason"]


@pytest.fixture
def firebase(monkeypatch):
    """A started Admin SDK whose verify_id_token answers what the test says."""
    monkeypatch.setattr(auth, "_firebase", object())

    def answer(result):
        def verify_id_token(token, app):
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(fb, "verify_id_token", verify_id_token)

    return answer


def test_no_token_is_not_signed_in():
    with pytest.raises(HTTPException) as e:
        auth.verify_token(None)
    assert refusal(e) == (401, "not_signed_in")
    assert e.value.headers == {"WWW-Authenticate": "Bearer"}


def test_no_key_is_unavailable(monkeypatch):
    monkeypatch.setattr(auth, "_firebase", None)
    with pytest.raises(HTTPException) as e:
        auth.verify_token(TOKEN)
    assert refusal(e) == (503, "auth_unavailable")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (fb.ExpiredIdTokenError("expired", cause=None), (401, "not_signed_in")),
        (fb.InvalidIdTokenError("wrong signature"), (401, "not_signed_in")),
        (ValueError("not a token"), (401, "not_signed_in")),
        (fb.CertificateFetchError("no keys", cause=None), (503, "auth_unavailable")),
    ],
)
def test_errors(firebase, error, expected):
    firebase(error)
    with pytest.raises(HTTPException) as e:
        auth.verify_token(TOKEN)
    assert refusal(e) == expected


def test_claims_pass_through(firebase):
    firebase({"uid": "u1", "phone_number": "+40700000001"})
    assert auth.verify_token(TOKEN) == {"uid": "u1", "phone_number": "+40700000001"}


def test_key_that_is_not_json_stops_startup(monkeypatch):
    monkeypatch.setattr(auth, "_firebase", None)
    with pytest.raises(SystemExit, match="not valid JSON"):
        auth.init_firebase("{not json")
