"""add app imports

Revision ID: 4def42029e96
Revises: c2fba4185b1c
Create Date: 2026-10-19 04:13:08.105242

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4def42029e96"
down_revision: str | Sequence[str] | None = "c2fba4185b1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("namespace", sa.String(length=63), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("plan_digest", sa.String(length=64), nullable=False),
        sa.Column("deployment", sa.JSON(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("namespace"),
    )


def downgrade() -> None:
    op.drop_table("app_imports")
