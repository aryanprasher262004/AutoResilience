"""add pod delete mode

Revision ID: 000336cc0672
Revises: 0363e45a3d5b
Create Date: 2026-10-06 15:56:04.105983

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "000336cc0672"
down_revision: str | Sequence[str] | None = "0363e45a3d5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Every experiment before this column ran FORCE=false, i.e. GRACEFUL.
    op.add_column(
        "experiments",
        sa.Column(
            "pod_delete_mode",
            sa.Enum(
                "GRACEFUL",
                "FORCE",
                name="pod_delete_mode",
                native_enum=False,
                length=16,
            ),
            server_default="GRACEFUL",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("experiments", "pod_delete_mode")
