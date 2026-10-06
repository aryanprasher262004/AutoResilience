"""add experiment observation

Revision ID: d43ecd782a89
Revises: 98573305f15d
Create Date: 2026-10-06 15:04:54.161340

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d43ecd782a89"
down_revision: str | Sequence[str] | None = "98573305f15d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("observation", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("experiments", "observation")
