"""The user row behind a grant (app/staff/service.py)."""

from sqlalchemy import func, select

from app.auth.service import user_for
from app.models import User

PHONE = "+40700000004"


async def test_a_new_number_gets_a_user(db):
    user = await user_for(db, PHONE, "Ioana Pop")
    await db.commit()
    assert (user.phone_e164, user.display_name) == (PHONE, "Ioana Pop")
    assert user.id is not None


async def test_a_known_number_keeps_its_user_and_name(db, add_user):
    known = await add_user(PHONE, name="Dr. Ioana Pop")
    user = await user_for(db, PHONE, "Ioana")
    await db.commit()
    assert user.id == known.id
    # Read back from the database: `user` is the object add_user already loaded,
    # so its attributes would show the old name even if the row had been renamed.
    stored = select(User.display_name).where(User.id == known.id)
    assert await db.scalar(stored) == "Dr. Ioana Pop"
    assert await db.scalar(select(func.count()).select_from(User)) == 1
