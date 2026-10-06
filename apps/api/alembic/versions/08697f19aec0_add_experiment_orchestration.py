"""add experiment orchestration

Revision ID: 08697f19aec0
Revises: 000336cc0672
Create Date: 2026-10-06 17:06:36.754048

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "08697f19aec0"
down_revision: str | Sequence[str] | None = "000336cc0672"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("orchestration", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("experiments", "orchestration")
