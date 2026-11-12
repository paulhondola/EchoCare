"""events.source

Record where an event came from (watch, phone or home_node, 04 §3) so the status engine
and dashboards can tell a wrist tap apart from a home-node press.

Revision ID: d8c1a2e4f7a0
Revises: 02b8952607c0
Create Date: 2026-11-12 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8c1a2e4f7a0"
down_revision: str | Sequence[str] | None = "02b8952607c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("events", sa.Column("source", sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("events", "source")
