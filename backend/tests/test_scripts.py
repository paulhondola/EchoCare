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
