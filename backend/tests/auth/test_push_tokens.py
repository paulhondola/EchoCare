import pytest
from sqlalchemy import select

from app.auth.models import PushToken
from app.models import Role

A = "+40700000001"
B = "+40700000002"
TOKEN = "fcm:abc-123_DEF"
PATH = f"/api/profile/push-tokens/{TOKEN}"


def signed_in(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def tokens(db):
    return (await db.scalars(select(PushToken))).all()


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize(
    ("headers", "status", "reason"),
    [
        ({}, 401, "not_signed_in"),
        (signed_in("+40700000009"), 403, "not_registered"),
    ],
)
async def test_signed_out_and_unknown(client, method, headers, status, reason):
    r = await client.request(method, PATH, headers=headers)
    assert (r.status_code, r.json()) == (status, {"detail": {"reason": reason}})
    if status == 401:
        assert r.headers["www-authenticate"] == "Bearer"


async def test_save_and_repeat(client, db, add_user):
    # PUT twice as A: 204, 204. One row, A's.
    a = await add_user(A, Role.das)
    for _ in range(2):
        r = await client.put(PATH, headers=signed_in(A))
        assert (r.status_code, r.content) == (204, b"")
    rows = await tokens(db)
    assert [(t.user_id, t.token) for t in rows] == [(a.id, TOKEN)]


async def test_a_token_moves_to_whoever_signs_in(client, db, add_user):
    # A PUTs the token, then B PUTs the same one (a shared tablet): one row, B's.
    await add_user(A, Role.das)
    b_id = (await add_user(B, Role.medic)).id
    first = await client.put(PATH, headers=signed_in(A))
    before = (await tokens(db))[0].updated_at
    second = await client.put(PATH, headers=signed_in(B))
    assert (first.status_code, second.status_code) == (204, 204)
    db.expire_all()
    rows = await tokens(db)
    assert [(t.user_id, t.token) for t in rows] == [(b_id, TOKEN)]
    assert rows[0].updated_at > before


async def test_only_your_own_token_is_dropped(client, db, add_user):
    # A PUTs. B DELETEs it: 204, row stays. A DELETEs: 204, gone. A again: 204.
    a_id = (await add_user(A, Role.das)).id
    await add_user(B, Role.medic)
    await client.put(PATH, headers=signed_in(A))
    r = await client.delete(PATH, headers=signed_in(B))
    assert r.status_code == 204
    assert [t.user_id for t in await tokens(db)] == [a_id]
    for _ in range(2):
        r = await client.delete(PATH, headers=signed_in(A))
        assert r.status_code == 204
    db.expire_all()
    assert await tokens(db) == []


async def test_a_token_too_long(client, add_user):
    # PUT a 513-character token: 422, so a 512-column never overflows.
    await add_user(A, Role.das)
    r = await client.put(f"/api/profile/push-tokens/{'x' * 513}", headers=signed_in(A))
    assert r.status_code == 422
