"""add experiment target, fault and validation result

Revision ID: 90b79844b9cf
Revises: d212b6a34d8b
Create Date: 2026-10-06 02:00:29.138451

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "90b79844b9cf"
down_revision: str | Sequence[str] | None = "d212b6a34d8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Pre-B2 experiments have no target and there is no meaningful value to backfill.
    existing = (
        op.get_bind().execute(sa.text("SELECT count(*) FROM experiments")).scalar()
    )
    if existing:
        raise RuntimeError(
            f"{existing} experiment(s) predate target/fault fields; "
            "delete them (dev data) before upgrading."
        )

    op.add_column(
        "experiments",
        sa.Column("target_namespace", sa.String(length=63), nullable=False),
    )
    op.add_column(
        "experiments",
        sa.Column(
            "target_kind",
            sa.Enum(
                "Deployment",
                "StatefulSet",
                name="workload_kind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
    )
    op.add_column(
        "experiments", sa.Column("target_name", sa.String(length=253), nullable=False)
    )
    op.add_column(
        "experiments",
        sa.Column(
            "fault_type",
            sa.Enum(
                "pod-delete",
                "pod-cpu-hog",
                "pod-memory-hog",
                "pod-network-latency",
                name="fault_type",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
    )
    op.add_column(
        "experiments", sa.Column("duration_seconds", sa.Integer(), nullable=False)
    )
    op.add_column(
        "experiments", sa.Column("affected_replicas", sa.Integer(), nullable=False)
    )
    op.add_column(
        "experiments", sa.Column("validation_result", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("experiments", "validation_result")
    op.drop_column("experiments", "affected_replicas")
    op.drop_column("experiments", "duration_seconds")
    op.drop_column("experiments", "fault_type")
    op.drop_column("experiments", "target_name")
    op.drop_column("experiments", "target_kind")
    op.drop_column("experiments", "target_namespace")
