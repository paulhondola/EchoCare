from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.settings import get_settings


class Base(DeclarativeBase):
    # No naming convention: alembic would apply it to the unnamed constraints of
    # 5d0c8c3a7f21, frozen on main, and fresh databases would differ from staging.
    # Tables name their constraints explicitly instead (app/models.py).
    pass


engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
# expire_on_commit=False: rows stay readable after a commit, since async code cannot
# lazy-load an expired attribute.
Session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """One session per request; FastAPI hands the same one to every dependency."""
    async with Session() as session:
        yield session
