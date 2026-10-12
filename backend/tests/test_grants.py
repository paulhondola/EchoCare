"""The user row behind a grant (app/grants.py)."""

from sqlalchemy import func, select

from app.grants import user_for_number
from app.models import User

PHONE = "+40700000004"


async def test_a_new_number_gets_a_user(db):
    user = await user_for_number(db, PHONE, "Ioana Pop")
    await db.commit()
    assert (user.phone_e164, user.display_name) == (PHONE, "Ioana Pop")
    assert user.id is not None


async def test_a_known_number_keeps_its_user_and_name(db, add_user):
    known = await add_user(PHONE, name="Dr. Ioana Pop")
    user = await user_for_number(db, PHONE, "Ioana")
    await db.commit()
    assert (user.id, user.display_name) == (known.id, "Dr. Ioana Pop")
    assert await db.scalar(select(func.count()).select_from(User)) == 1
