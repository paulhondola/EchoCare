import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Grant, Role

BACKEND = Path(__file__).parent.parent


def test_models_match_the_migration(migrated):
    # `alembic check` fails when autogenerate would add anything (auth-layer §4).
    subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=BACKEND, check=True)


async def test_ids_are_uuid_v7(add_user):
    user = await add_user("+40700000001")
    assert user.id.version == 7


async def test_one_grant_per_role(db, add_user):
    user = await add_user("+40700000001", Role.das)
    db.add(Grant(user_id=user.id, role=Role.das))
    with pytest.raises(IntegrityError):
        await db.commit()


@pytest.mark.parametrize(
    ("role", "senior_id"),
    [
        (Role.caregiver, None),  # a caregiver grant names its senior
        (Role.senior, None),
        (Role.das, uuid.uuid4()),  # a staff grant names none
        ("boss", None),  # only the four roles
    ],
)
async def test_grant_checks(db, add_user, role, senior_id):
    user = await add_user("+40700000001")
    db.add(Grant(user_id=user.id, role=role, senior_id=senior_id))
    with pytest.raises(IntegrityError):
        await db.commit()
