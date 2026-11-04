"""seniors.submitted_at, accepted_at, accepted_by

When the medic submitted the enrollment, when DAS accepted it and which DAS user did
(05 §1); the medic panel's queue and its "waiting since" read them.

Revision ID: e1a5b7c3d904
Revises: c7a4e2f95d18
Create Date: 2026-11-04 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1a5b7c3d904"
down_revision: str | Sequence[str] | None = "c7a4e2f95d18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "seniors",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "seniors",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("seniors", sa.Column("accepted_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "seniors_accepted_by_fkey", "seniors", "users", ["accepted_by"], ["id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("seniors_accepted_by_fkey", "seniors", type_="foreignkey")
    op.drop_column("seniors", "accepted_by")
    op.drop_column("seniors", "accepted_at")
    op.drop_column("seniors", "submitted_at")
