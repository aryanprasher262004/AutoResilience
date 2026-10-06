import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.domain.experiment import FaultType, PodDeleteMode, WorkloadKind
from app.schemas.history import ExperimentSummary, ScorePoint

# HEALTHY: ready >= desired · DEGRADED: some ready · UNAVAILABLE: none ready
# SCALED_TO_ZERO: desired 0 · NOT_FOUND: no longer in the cluster
# UNKNOWN: the cluster could not be queried
WorkloadHealth = Literal[
    "HEALTHY", "DEGRADED", "UNAVAILABLE", "SCALED_TO_ZERO", "NOT_FOUND", "UNKNOWN"
]


class LatestScore(BaseModel):
    """The most recent experiment on this workload that produced a numeric score."""

    experiment_id: uuid.UUID
    score: float
    rating: str | None
    status: str
    version: str
    at: datetime


class ServiceSummary(BaseModel):
    namespace: str
    kind: WorkloadKind
    name: str
    desired_replicas: int
    current_replicas: int
    ready_replicas: int
    available_replicas: int
    health: WorkloadHealth
    created_at: datetime | None
    experiment_count: int
    latest_experiment: ExperimentSummary | None
    latest_score: LatestScore | None


class ServiceList(BaseModel):
    items: list[ServiceSummary]
    # System namespaces left out of discovery (and refused by every safety policy).
    excluded_namespaces: list[str]


class LiveStatus(BaseModel):
    """Pod-level status, read the same way safety validation reads it."""

    desired_replicas: int
    running_pods: int
    ready_pods: int
    ready_pod_names: list[str]


class FaultCoverage(BaseModel):
    fault_type: FaultType
    pod_delete_mode: PodDeleteMode
    runs: int
    completed: int
    last_run_at: datetime
    latest_score: LatestScore | None


class ServiceDetail(BaseModel):
    namespace: str
    kind: WorkloadKind
    name: str
    health: WorkloadHealth
    live: LiveStatus | None
    cluster_error: str | None
    experiment_count: int
    latest_score: LatestScore | None
    faults: list[FaultCoverage]
    # Current scoring methodology only, oldest first (see GET /dashboard/summary).
    score_version: str
    score_history: list[ScorePoint]
    # Newest first, at most `limit` (see experiment_count for the total).
    experiments: list[ExperimentSummary]
