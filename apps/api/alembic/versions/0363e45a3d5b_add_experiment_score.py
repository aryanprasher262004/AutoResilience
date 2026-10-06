"""add experiment score

Revision ID: 0363e45a3d5b
Revises: d43ecd782a89
Create Date: 2026-10-06 15:17:19.019532

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0363e45a3d5b"
down_revision: str | Sequence[str] | None = "d43ecd782a89"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("score", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("experiments", "score")
