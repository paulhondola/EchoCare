"""home_node_states

The home node's latest room reading, one row per senior with a node (P20, P21, 05 §2).

Revision ID: a4f2c8e1b9d3
Revises: 620c34d28419
Create Date: 2026-11-14 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a4f2c8e1b9d3"
down_revision: str | Sequence[str] | None = "620c34d28419"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "home_node_states",
        sa.Column("senior_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("last_reading_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("humidity_pct", sa.Float(), nullable=True),
        sa.Column("last_motion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forecast_60m_c", sa.Float(), nullable=True),
        sa.Column("out_of_range_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "out_of_range_event_sent",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["senior_id"], ["seniors.id"]),
        sa.PrimaryKeyConstraint("senior_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("home_node_states")
