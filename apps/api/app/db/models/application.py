import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Application(Base):
    """An onboarded application: a named, namespace-scoped view of one cluster.

    Only a record of what to show. Creating or deleting it never touches the
    cluster; experiments still target individual workloads.
    """

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # The kubeconfig context; None: the engine's execution context while KUBE_CONTEXT
    # is unset (development only).
    kube_context: Mapped[str | None] = mapped_column(String(253))
    namespaces: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
