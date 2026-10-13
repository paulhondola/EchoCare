import enum
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, TypeDecorator, Uuid, func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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


class StoredEnum(TypeDecorator):
    """An enum in a VARCHAR(32), by member name, so Severity and Certainty store 'green'
    and 'high', not 0 and 2. An unknown name, written by a newer copy during a deploy or
    before a rollback, reads back as the bare string (ADR-001 §2.3).
    """

    impl = String
    cache_ok = True

    def __init__(self, cls: type[enum.Enum]) -> None:
        super().__init__(length=32)
        self.cls = cls

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return value.name if isinstance(value, enum.Enum) else value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return value if value is None else self.cls.__members__.get(value, value)


def enum_type(cls: type[enum.Enum]) -> StoredEnum:
    return StoredEnum(cls)


def in_states(column: str, states: frozenset[Any]) -> Any:
    """A partial index predicate over a set of enum members, in a stable order."""
    names = ", ".join(f"'{name}'" for name in sorted(state.name for state in states))
    return text(f"{column} IN ({names})")


def uuid_pk() -> Mapped[uuid.UUID]:
    # Time-ordered, so new rows land at the end of the primary key index.
    return mapped_column(Uuid, primary_key=True, server_default=text("uuidv7()"))


def timestamp_now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())
