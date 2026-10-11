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


MANGLED_KEY = (
    '{"type": "service_account", "project_id": "p", "private_key_id": "k",'
    ' "private_key": "-----BEGIN PRIVATE KEY-----\\nnot a key\\n'
    '-----END PRIVATE KEY-----\\n", "client_email": "a@p.iam.gserviceaccount.com",'
    ' "client_id": "1", "token_uri": "https://oauth2.googleapis.com/token"}'
)


@pytest.mark.parametrize(
    "service_account",
    [
        "{not json",  # pasted across lines, or without its quotes
        "{}",  # another JSON file, such as google-services.json
        "[]",
        '"x"',  # a JSON string, which Certificate would read as a file path
        MANGLED_KEY,  # the private key's \n escapes lost on the way
    ],
)
def test_a_key_that_is_not_a_service_account_stops_startup(
    monkeypatch, service_account
):
    monkeypatch.setattr(auth, "_firebase", None)
    with pytest.raises(SystemExit, match="FIREBASE_SERVICE_ACCOUNT"):
        auth.init_firebase(service_account)
