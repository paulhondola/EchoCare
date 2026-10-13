import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, timestamp_now, uuid_pk


class Role(StrEnum):
    das = "das"
    medic = "medic"
    caregiver = "caregiver"
    senior = "senior"


# The order of GET /me's grants (auth-layer §3.3).
ROLE_ORDER = list(Role)

# Grants that apply to one senior; das and medic grants apply to none (05 §1).
SENIOR_ROLES = frozenset({Role.caregiver, Role.senior})


class User(Base):
    """One row per phone number granted anything, made before first sign-in (05 §4)."""

    __tablename__ = "users"
    __table_args__ = (
        # Constraints carry the names their migration gave them, so `alembic check`
        # matches: Postgres's own in 5d0c8c3a7f21, uq_ and ck_ ones after it.
        # Its unique index serves the lookup on every request (auth-layer §3.1).
        UniqueConstraint("phone_e164", name="users_phone_e164_key"),
        # Replaced, with a warning, if another Firebase account signs in with it (AL4).
        UniqueConstraint("firebase_uid", name="users_firebase_uid_key"),
        # At most one DAS employee on duty (P10).
        Index(
            "uq_users_on_duty",
            "on_duty",
            unique=True,
            postgresql_where=text("on_duty"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    phone_e164: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(120))
    firebase_uid: Mapped[str | None] = mapped_column(String(128))
    practice: Mapped[str | None] = mapped_column(String(200))  # medics
    on_duty: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = timestamp_now()


class Grant(Base):
    """One role for one user; caregiver and senior grants name their senior (AL5)."""

    __tablename__ = "grants"
    __table_args__ = (
        # NULLS NOT DISTINCT: a das or medic grant, whose senior_id is NULL, is also
        # unique per user. Starting with user_id, it serves the per-request grant lookup.
        UniqueConstraint(
            "user_id",
            "role",
            "senior_id",
            name="grants_user_id_role_senior_id_key",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "role IN ('das', 'medic', 'caregiver', 'senior')", name="role_known"
        ),
        CheckConstraint(
            "(role IN ('caregiver', 'senior')) = (senior_id IS NOT NULL)",
            name="senior_only_for_senior_roles",
        ),
        # At most one senior grant per user (AL7).
        Index(
            "uq_grants_one_senior_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("role = 'senior'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    # Revoking a grant deletes it, so access stops at once (05 §5).
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))
    # The foreign key arrived with the seniors table (AL6).
    senior_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seniors.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str | None] = mapped_column(String(60))  # caregivers
    # Empty for grants made by the setup script (G6).
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = timestamp_now()


class PushToken(Base):
    """Where to deliver pushes for a user, one row per device (G4)."""

    __tablename__ = "push_tokens"
    __table_args__ = (UniqueConstraint("token", name="uq_push_tokens_token"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # A device's token belongs to whoever signed in on it last.
    token: Mapped[str] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
