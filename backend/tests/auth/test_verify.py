import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from firebase_admin import auth as fb

from app.auth.service import verify_token

TOKEN = HTTPAuthorizationCredentials(scheme="Bearer", credentials="a.b.c")


def refusal(e: pytest.ExceptionInfo[HTTPException]) -> tuple[int, str]:
    return e.value.status_code, e.value.detail["reason"]


@pytest.fixture
def firebase(monkeypatch):
    """An Admin SDK whose verify_id_token answers what the test says."""

    def answer(result):
        def verify_id_token(token, app):
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(fb, "verify_id_token", verify_id_token)

    return answer


def test_no_token_is_not_signed_in():
    with pytest.raises(HTTPException) as e:
        verify_token(None)
    assert refusal(e) == (401, "not_signed_in")
    assert e.value.headers == {"WWW-Authenticate": "Bearer"}


def test_verifies_without_a_key():
    """No service account (auth-layer AL11): a bad token is refused for what it is,
    not for want of a credential."""
    with pytest.raises(HTTPException) as e:
        verify_token(TOKEN)
    assert refusal(e) == (401, "not_signed_in")


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
        verify_token(TOKEN)
    assert refusal(e) == expected


def test_claims_pass_through(firebase):
    firebase({"uid": "u1", "phone_number": "+40700000001"})
    assert verify_token(TOKEN) == {"uid": "u1", "phone_number": "+40700000001"}
