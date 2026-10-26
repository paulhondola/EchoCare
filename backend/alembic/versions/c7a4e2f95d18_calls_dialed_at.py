"""calls.dialed_at

Stamped and committed before Twilio is asked to dial; from then on the status callback,
not a campaign's end or the senior's card, settles the call.

Revision ID: c7a4e2f95d18
Revises: b3e9c1d47a52
Create Date: 2026-10-24 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7a4e2f95d18"
down_revision: str | Sequence[str] | None = "b3e9c1d47a52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "calls", sa.Column("dialed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("calls", "dialed_at")
