"""add experiment baseline

Revision ID: d369e0debbe0
Revises: 90b79844b9cf
Create Date: 2026-10-06 02:24:34.252604

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d369e0debbe0"
down_revision: str | Sequence[str] | None = "90b79844b9cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("baseline", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("experiments", "baseline")
