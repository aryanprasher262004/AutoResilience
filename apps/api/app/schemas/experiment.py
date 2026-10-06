import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.experiment import FaultType, PodDeleteMode, WorkloadKind
from app.domain.state_machine import ExperimentState
from app.services.orchestration.baseline import BaselineStatus, MetricStatus
from app.services.safety.policy_evaluator import CheckStatus

# Kubernetes naming rules (RFC 1123), checked statically before anything is stored.
DNS_LABEL = r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
DNS_SUBDOMAIN = r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$"


class ExperimentTargetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    namespace: str = Field(min_length=1, max_length=63, pattern=DNS_LABEL)
    kind: WorkloadKind
    name: str = Field(min_length=1, max_length=253, pattern=DNS_SUBDOMAIN)


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    target: ExperimentTargetSchema
    fault_type: FaultType
    duration_seconds: int = Field(gt=0)
    affected_replicas: int = Field(gt=0)
    # Only GRACEFUL or FORCE; omitted means GRACEFUL (the behaviour before modes).
    pod_delete_mode: PodDeleteMode = PodDeleteMode.GRACEFUL


class ValidationCheckRead(BaseModel):
    name: str
    status: CheckStatus
    message: str


class ValidationResultRead(BaseModel):
    passed: bool
    static_checks: list[ValidationCheckRead]
    cluster_checks: list[ValidationCheckRead]
    policy: dict[str, object]


class MetricGroupRead(BaseModel):
    status: MetricStatus
    message: str
    values: dict[str, float | int | None]


class BaselineRead(BaseModel):
    status: BaselineStatus
    captured_at: datetime
    window_seconds: int
    availability: MetricGroupRead
    restarts: MetricGroupRead
    requests: MetricGroupRead
    # Absent on baselines captured before client-side measurement existed.
    client: MetricGroupRead | None = None
    failure_reasons: list[str]


class ChaosRead(BaseModel):
    provider: str
    experiment: str
    pod_delete_mode: PodDeleteMode | None = None  # absent on pre-mode records
    engine_name: str | None = None
    namespace: str | None = None
    target_pods: list[str] = []
    duration_seconds: int | None = None
    created_at: datetime | None = None
    injected_at: datetime | None = None
    status: dict[str, str | None] | None = None
    failure_reason: str | None = None
    stopped: bool | None = None
    stop_error: str | None = None


class ObservationResultRead(BaseModel):
    status: str  # IN_PROGRESS | COMPLETED | UNKNOWN
    reason_code: str | None = None
    reason: str | None = None
    cause: str | None = None  # platform | application | conflicting_evidence


class ObservationRead(BaseModel):
    rule: str
    evaluations: int
    updated_at: datetime
    result: ObservationResultRead
    litmus: dict[str, Any] | None = None
    recovery: dict[str, Any] | None = None
    impact: dict[str, Any] | None = None
    target: dict[str, Any] | None = None
    last_error: str | None = None


class ScoreComponentRead(BaseModel):
    name: str
    status: str  # SCORED | NOT_APPLICABLE
    raw: dict[str, Any]
    normalized: float | None
    weight: float
    effective_weight: float
    contribution: float
    reason: str


class ScoreRead(BaseModel):
    version: str
    status: str  # SCORED | SCORED_NOT_RECOVERED | NOT_SCORED
    score: float | None
    rating: str | None
    explanation: str
    components: list[ScoreComponentRead]
    cap_applied: dict[str, float] | None = None
    weights: dict[str, float] | None = None
    thresholds: dict[str, float] | None = None
    inputs: dict[str, Any]


class ExperimentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    state: ExperimentState
    target: ExperimentTargetSchema
    fault_type: FaultType
    duration_seconds: int
    affected_replicas: int
    pod_delete_mode: PodDeleteMode
    validation_result: ValidationResultRead | None
    baseline: BaselineRead | None
    chaos: ChaosRead | None
    observation: ObservationRead | None
    score: ScoreRead | None
    created_at: datetime
    updated_at: datetime
