"""health readings

Revision ID: 329ac5f45360
Revises: a4d7e2b9c615
Create Date: 2026-11-14 22:03:12.154802

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "329ac5f45360"
down_revision: str | Sequence[str] | None = "a4d7e2b9c615"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "health_readings",
        sa.Column("senior_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("spo2", sa.Integer(), nullable=True),
        sa.Column("ecg_classification", sa.String(length=32), nullable=True),
        sa.Column("ecg_heart_rate", sa.Integer(), nullable=True),
        sa.Column("ecg_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ecg_trace_hz", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["senior_id"],
            ["seniors.id"],
        ),
        sa.PrimaryKeyConstraint("senior_id", "id"),
    )
    op.create_index(
        "ix_health_readings_senior_measured",
        "health_readings",
        ["senior_id", "measured_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_health_readings_senior_measured", table_name="health_readings")
    op.drop_table("health_readings")
