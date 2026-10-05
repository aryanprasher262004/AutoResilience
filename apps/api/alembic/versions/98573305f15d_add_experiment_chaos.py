"""add experiment chaos

Revision ID: 98573305f15d
Revises: d369e0debbe0
Create Date: 2026-10-06 02:50:42.363170

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "98573305f15d"
down_revision: str | Sequence[str] | None = "d369e0debbe0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("chaos", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("experiments", "chaos")
