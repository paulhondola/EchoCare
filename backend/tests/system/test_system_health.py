from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError

from app.core.settings import get_settings
from app.models import Role

DAS = "+40700000001"
MEDIC = "+40700000002"


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_system_health_unauthenticated(client):
    r = await client.get("/api/system/health")
    assert r.status_code == 401
    assert r.json() == {"detail": {"reason": "not_signed_in"}}


async def test_system_health_refuses_non_das(client, add_user):
    await add_user(MEDIC, Role.medic)
    r = await client.get("/api/system/health", headers=signed_in(MEDIC))
    assert r.status_code == 403
    assert r.json() == {"detail": {"reason": "not_allowed"}}


async def test_system_health_success_for_das(client, add_user):
    await add_user(DAS, Role.das)
    r = await client.get("/api/system/health", headers=signed_in(DAS))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "env" in data
    assert data["database"]["status"] == "ok"
    assert isinstance(data["database"]["latency_ms"], float)
    assert data["database"]["latency_ms"] >= 0
    assert "timestamp" in data


async def test_system_health_degraded_when_db_down(client, add_user):
    await add_user(DAS, Role.das)
    with patch(
        "app.system.router.check_database_health",
        side_effect=OperationalError("mock", {}, Exception()),
    ):
        r = await client.get("/api/system/health", headers=signed_in(DAS))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "degraded"
    assert data["database"]["status"] == "unreachable"
    assert isinstance(data["database"]["latency_ms"], float)


async def test_health_is_open_and_reports_the_env(client):
    # Railway's health check signs in as nobody (06 §1).
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "env": get_settings().app_env}


async def test_health_fails_when_db_down(client):
    # A failing check holds back a broken deploy (06 §1).
    with (
        patch(
            "app.system.router.check_database_health",
            side_effect=OperationalError("mock", {}, Exception()),
        ),
        pytest.raises(OperationalError),
    ):
        await client.get("/api/health")
