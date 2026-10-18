import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AppImport(Base):
    """An imported application (P7): its reviewed spec, plan and deployment state.

    Holds no file contents, environment values or credentials: only the normalized
    spec (allowlisted fields), the findings, and the plan rendered from that spec.
    """

    __tablename__ = "app_imports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    source: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str | None] = mapped_column(String(255))
    # PLANNED | DEPLOYING | READY | FAILED | REMOVING | REMOVED (services/imports/lifecycle.py)
    status: Mapped[str] = mapped_column(String(20), default="PLANNED")
    namespace: Mapped[str] = mapped_column(String(63), unique=True)
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON)
    plan_digest: Mapped[str] = mapped_column(String(64))
    deployment: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("applications.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
