import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.experiment import FaultType, WorkloadKind
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
    failure_reasons: list[str]


class ChaosRead(BaseModel):
    provider: str
    experiment: str
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
    validation_result: ValidationResultRead | None
    baseline: BaselineRead | None
    chaos: ChaosRead | None
    created_at: datetime
    updated_at: datetime
