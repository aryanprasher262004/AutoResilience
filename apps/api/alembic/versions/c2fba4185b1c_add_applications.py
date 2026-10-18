"""add applications

Revision ID: c2fba4185b1c
Revises: 08697f19aec0
Create Date: 2026-10-18 22:55:44.431105

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2fba4185b1c"
down_revision: str | Sequence[str] | None = "08697f19aec0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kube_context", sa.String(length=253), nullable=True),
        sa.Column("namespaces", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("applications")
