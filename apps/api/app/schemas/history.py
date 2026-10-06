import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.experiment import FaultType, PodDeleteMode
from app.domain.state_machine import ExperimentState
from app.schemas.experiment import ExperimentTargetSchema


class ScoreSummary(BaseModel):
    score: float | None
    rating: str | None
    status: str
    version: str


class ExperimentSummary(BaseModel):
    """Slim experiment row for history lists and dashboards (no evidence JSON)."""

    id: uuid.UUID
    name: str
    target: ExperimentTargetSchema
    fault_type: FaultType
    pod_delete_mode: PodDeleteMode
    affected_replicas: int
    duration_seconds: int
    state: ExperimentState
    auto: bool
    has_baseline: bool
    score: ScoreSummary | None
    time_to_recovery_seconds: float | None
    client_outage_seconds: float | None
    outcome_reason: str | None
    created_at: datetime
    updated_at: datetime


class ExperimentPage(BaseModel):
    items: list[ExperimentSummary]
    total: int
    limit: int
    offset: int


class OutcomeCounts(BaseModel):
    active: int
    completed: int
    failed: int  # VALIDATION_FAILED + INJECTION_FAILED
    aborted: int
    undetermined: int  # UNKNOWN


class Distribution(BaseModel):
    count: int
    median: float | None
    minimum: float | None
    maximum: float | None


class ScoreStats(BaseModel):
    version: str  # stats only use this (current) methodology version
    count: int
    average: float | None
    minimum: float | None
    maximum: float | None
    by_rating: dict[str, int]
    not_recovered: int  # SCORED_NOT_RECOVERED, included in the stats above
    not_scored: int  # NOT_SCORED records (platform/conflicting UNKNOWN)
    other_versions: int  # scored with an older methodology, excluded


class ScorePoint(BaseModel):
    experiment_id: uuid.UUID
    name: str
    namespace: str
    workload: str
    at: datetime
    score: float
    rating: str | None


class NamespaceStats(BaseModel):
    namespace: str
    total: int
    completed: int
    last_activity: datetime


class DashboardSummary(BaseModel):
    total: int
    by_state: dict[str, int]
    outcomes: OutcomeCounts
    scores: ScoreStats
    recovery_time_seconds: Distribution  # COMPLETED runs with a measured recovery
    client_outage_seconds: Distribution  # runs with a measured client outage
    score_history: list[ScorePoint]  # scored runs (current version), oldest first
    namespaces: list[NamespaceStats]
    recent: list[ExperimentSummary]
