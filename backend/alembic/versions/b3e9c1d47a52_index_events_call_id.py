"""index events.call_id

GET /incidents/{id} looks up the events attached to an incident's calls (04 §1), and
events are kept (05 §5).

Revision ID: b3e9c1d47a52
Revises: 741f75a7dbe1
Create Date: 2026-10-12 21:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3e9c1d47a52"
down_revision: str | Sequence[str] | None = "741f75a7dbe1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f("ix_events_call_id"), "events", ["call_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_events_call_id"), table_name="events")
