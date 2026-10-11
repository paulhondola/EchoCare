"""Tables (05), only those the built features use: the auth layer's (auth-layer §4).

The database makes every row id with uuidv7(), built into Postgres 18 (04 §0).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Role(StrEnum):
    das = "das"
    medic = "medic"
    caregiver = "caregiver"
    senior = "senior"


# The order of GET /me's grants (auth-layer §3.3).
ROLE_ORDER = list(Role)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, server_default=text("uuidv7()"))


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """One row per phone number granted anything, made before first sign-in (05 §4)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Its unique index serves the lookup on every request (auth-layer §3.1).
    phone_e164: Mapped[str] = mapped_column(String(16), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    # Replaced, with a warning, if another Firebase account signs in with the number (AL4).
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True)
    practice: Mapped[str | None] = mapped_column(String(200))  # medics
    created_at: Mapped[datetime] = created_at()


class Grant(Base):
    """One role for one user; caregiver and senior grants name their senior (AL5)."""

    __tablename__ = "grants"
    __table_args__ = (
        # NULLS NOT DISTINCT: a das or medic grant, whose senior_id is NULL, is also
        # unique per user. Starting with user_id, it serves the per-request grant lookup.
        UniqueConstraint(
            "user_id", "role", "senior_id", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint(
            "role IN ('das', 'medic', 'caregiver', 'senior')", name="role_known"
        ),
        CheckConstraint(
            "(role IN ('caregiver', 'senior')) = (senior_id IS NOT NULL)",
            name="senior_only_for_senior_roles",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Revoking a grant deletes it, so access stops at once (05 §5).
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    # No foreign key until the seniors table exists (AL6).
    senior_id: Mapped[uuid.UUID | None]
    relation: Mapped[str | None] = mapped_column(String(60))  # caregivers
    # Empty for grants made by the setup script (G6).
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at()
