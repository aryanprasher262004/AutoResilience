import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.experiment import (
    ExperimentSpec,
    ExperimentTarget,
    FaultType,
    WorkloadKind,
)
from app.domain.state_machine import INITIAL_STATE, ExperimentState


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[ExperimentState] = mapped_column(
        Enum(ExperimentState, native_enum=False, length=32, name="experiment_state"),
        default=INITIAL_STATE,
        index=True,
    )

    target_namespace: Mapped[str] = mapped_column(String(63))
    target_kind: Mapped[WorkloadKind] = mapped_column(
        Enum(
            WorkloadKind,
            native_enum=False,
            length=32,
            name="workload_kind",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    target_name: Mapped[str] = mapped_column(String(253))
    fault_type: Mapped[FaultType] = mapped_column(
        Enum(
            FaultType,
            native_enum=False,
            length=64,
            name="fault_type",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    duration_seconds: Mapped[int] = mapped_column(Integer)
    affected_replicas: Mapped[int] = mapped_column(Integer)
    # Output of the last safety validation (checks, reasons, policy snapshot).
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Last baseline capture (CAPTURED or FAILED, with per-metric-group results).
    baseline: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Fault injection record: Litmus engine identity, target pods, status, failure.
    chaos: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Observation/recovery evidence: Litmus outcome, recovery finding, impact, result.
    observation: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    @property
    def target(self) -> ExperimentTarget:
        return ExperimentTarget(
            namespace=self.target_namespace,
            kind=self.target_kind,
            name=self.target_name,
        )

    @property
    def spec(self) -> ExperimentSpec:
        return ExperimentSpec(
            target=self.target,
            fault_type=self.fault_type,
            duration_seconds=self.duration_seconds,
            affected_replicas=self.affected_replicas,
        )
