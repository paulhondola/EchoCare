"""watch_readings, watch_states.resting_pulse/steps_today/minutes_without_steps

DAS sees the watch, and the dashboard draws the last 24 hours of pulse (ADR-006). The
unique key drops a check-in the phone relays twice, and its index serves the 24-hour read.

Revision ID: 15cc782d0752
Revises: d8c1a2e4f7a0
Create Date: 2026-11-13 11:26:48.765647

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "15cc782d0752"
down_revision: str | Sequence[str] | None = "d8c1a2e4f7a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watch_readings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("senior_id", sa.Uuid(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pulse", sa.Integer(), nullable=True),
        sa.Column("resting_pulse", sa.Integer(), nullable=True),
        sa.Column("steps_today", sa.Integer(), nullable=True),
        sa.Column("battery", sa.Integer(), nullable=True),
        sa.Column("worn", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["senior_id"], ["seniors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("senior_id", "measured_at"),
    )
    op.add_column(
        "watch_states", sa.Column("resting_pulse", sa.Integer(), nullable=True)
    )
    op.add_column("watch_states", sa.Column("steps_today", sa.Integer(), nullable=True))
    op.add_column(
        "watch_states",
        sa.Column("minutes_without_steps", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("watch_states", "minutes_without_steps")
    op.drop_column("watch_states", "steps_today")
    op.drop_column("watch_states", "resting_pulse")
    op.drop_table("watch_readings")
