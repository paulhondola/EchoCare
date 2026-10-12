"""The user row behind a grant (01 §6): made when a number is first granted anything."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def user_for_number(
    session: AsyncSession, phone_e164: str, display_name: str
) -> User:
    """The number's user, made with `display_name` if the number has none.

    A user that exists keeps their name (auth-layer §3.4). The insert is ON CONFLICT
    DO NOTHING, so two grants of one new number at the same moment make one row.
    """
    await session.execute(
        insert(User)
        .values(phone_e164=phone_e164, display_name=display_name)
        .on_conflict_do_nothing(index_elements=[User.phone_e164])
    )
    found = await session.scalars(select(User).where(User.phone_e164 == phone_e164))
    return found.one()
