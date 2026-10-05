"""create experiments table

Revision ID: d212b6a34d8b
Revises:
Create Date: 2026-10-06 01:55:21.083387

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d212b6a34d8b"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "CREATED",
                "VALIDATING",
                "BASELINING",
                "INJECTING",
                "OBSERVING",
                "RECOVERING",
                "COMPLETED",
                "VALIDATION_FAILED",
                "INJECTION_FAILED",
                "ABORTED",
                "UNKNOWN",
                name="experiment_state",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_experiments_state"), "experiments", ["state"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_experiments_state"), table_name="experiments")
    op.drop_table("experiments")
