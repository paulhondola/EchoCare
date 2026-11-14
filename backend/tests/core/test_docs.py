"""No OpenAPI docs in production (design 2026-11-14): the API surface stays unlisted."""

from app.core.settings import AppEnv
from app.main import docs_urls


def test_docs_hidden_in_production():
    assert docs_urls(AppEnv.production) == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def test_docs_shown_off_production():
    for env in (AppEnv.local, AppEnv.staging):
        assert docs_urls(env) == {
            "docs_url": "/api/docs",
            "redoc_url": "/api/redoc",
            "openapi_url": "/api/openapi.json",
        }
