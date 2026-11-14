"""seniors.equipment

The equipment the medic declared at registration: smartphone, watch, home node (05 §1,
design 2026-11-14). Null for every senior registered before, which reads as not stated.

Revision ID: a4d7e2b9c615
Revises: 620c34d28419
Create Date: 2026-11-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4d7e2b9c615"
down_revision: str | Sequence[str] | None = "620c34d28419"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "seniors",
        sa.Column("equipment", postgresql.ARRAY(sa.String(length=20)), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("seniors", "equipment")
