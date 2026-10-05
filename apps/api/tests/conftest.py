from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.experiments import (
    get_baseline_window_seconds,
    get_chaos_provider,
    get_kubernetes_adapter,
    get_prometheus_client,
    get_start_wait,
)
from app.db import models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base
from app.db.session import get_db
from app.domain.experiment import ExperimentTarget, WorkloadKind
from app.integrations.chaos_provider import (
    ChaosProviderError,
    FaultPhase,
    FaultStatus,
    PodDeleteRequest,
    engine_name,
)
from app.integrations.kubernetes_adapter import ClusterUnavailableError, WorkloadStatus
from app.integrations.prometheus_client import PrometheusError
from app.main import app
from app.services.orchestration.baseline import baseline_queries
from app.services.orchestration.injection import StartWait

CHECKOUT_PODS = ("checkout-a", "checkout-b", "checkout-c")


class FakeKubernetes:
    """Stands in for KubernetesAdapter; defaults to a healthy 3-replica workload.

    `live_sequence` scripts live_pod_names(): one entry per call, last one repeats.
    Default: targeted pods are already gone on the first check.
    """

    def __init__(self) -> None:
        self.status: WorkloadStatus | None = WorkloadStatus(
            3, 3, 3, selector="app=checkout", ready_pod_names=CHECKOUT_PODS
        )
        self.error: str | None = None
        self.calls: list[ExperimentTarget] = []
        self.live_sequence: list[set[str] | Exception] = [set()]
        self.live_calls: list[list[str]] = []

    def get_workload_status(self, target: ExperimentTarget) -> WorkloadStatus | None:
        self.calls.append(target)
        if self.error is not None:
            raise ClusterUnavailableError(self.error)
        return self.status

    def live_pod_names(self, namespace: str, names: list[str]) -> set[str]:
        self.live_calls.append(names)
        result = self.live_sequence[
            min(len(self.live_calls), len(self.live_sequence)) - 1
        ]
        if isinstance(result, Exception):
            raise result
        return result & set(names)


def fault(phase: FaultPhase, verdict: str | None = "Awaited") -> FaultStatus:
    experiment_status = {
        FaultPhase.PENDING: "Waiting for Job Creation",
        FaultPhase.RUNNING: "Running",
        FaultPhase.COMPLETED: "Completed",
        FaultPhase.FAILED: "Completed",
    }[phase]
    return FaultStatus(phase, "initialized", experiment_status, verdict, "pod-delete-x")


class FakeChaos:
    """Stands in for LitmusChaosProvider. `statuses` scripts get_status() per call."""

    def __init__(self) -> None:
        self.requests: list[PodDeleteRequest] = []
        self.start_error: str | None = None
        self.statuses: list[FaultStatus | Exception] = [
            fault(FaultPhase.PENDING),
            fault(FaultPhase.RUNNING),
        ]
        self.status_calls = 0
        self.stopped: list[tuple[str, str]] = []
        self.stop_error: str | None = None

    def start_pod_delete(self, request: PodDeleteRequest) -> str:
        if self.start_error is not None:
            raise ChaosProviderError(self.start_error)
        self.requests.append(request)
        return engine_name(request.experiment_id)

    def get_status(self, namespace: str, name: str) -> FaultStatus:
        self.status_calls += 1
        result = self.statuses[min(self.status_calls, len(self.statuses)) - 1]
        if isinstance(result, Exception):
            raise result
        return result

    def stop(self, namespace: str, name: str) -> None:
        if self.stop_error is not None:
            raise ChaosProviderError(self.stop_error)
        self.stopped.append((namespace, name))


# No real sleeping in tests: up to 10 polls.
FAST_WAIT = StartWait(timeout_seconds=10, poll_interval_seconds=1, sleep=lambda _: None)


HEALTHY_BASELINE: dict[str, float | None] = {
    "desired_replicas": 2,
    "available_replicas_avg": 2,
    "available_replicas_min": 2,
    "availability_samples": 20,
    "restarts_total": 1,
    "restarts_in_window": 0,
    "request_series": 2,
    "request_rate_rps": 1.5,
    "error_rate_rps": None,  # no 5xx series recorded
}


# The target used by API tests (see tests/api/test_experiments.py::payload).
CHECKOUT = ExperimentTarget("shop", WorkloadKind.DEPLOYMENT, "checkout")
WINDOW_SECONDS = 300


class FakePrometheus:
    """Answers the baseline queries for one target by query name; defaults are healthy.

    Set a value to None for an empty result or to an exception to raise it;
    set `error` to fail every query.
    """

    def __init__(
        self, target: ExperimentTarget = CHECKOUT, window_seconds: int = WINDOW_SECONDS
    ) -> None:
        self.values: dict[str, float | None | Exception] = dict(HEALTHY_BASELINE)
        self.error: str | None = None
        self.queries: list[tuple[str, datetime]] = []
        self._names = {
            promql: name
            for name, promql in baseline_queries(target, window_seconds).items()
        }

    def query_value(self, promql: str, at: datetime) -> float | None:
        self.queries.append((promql, at))
        if self.error is not None:
            raise PrometheusError(self.error)
        result = self.values[self._names[promql]]
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def db_session() -> Iterator[Session]:
    # In-memory SQLite shared across connections; each test gets a fresh schema.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def kubernetes() -> FakeKubernetes:
    return FakeKubernetes()


@pytest.fixture
def prometheus() -> FakePrometheus:
    return FakePrometheus()


@pytest.fixture
def chaos() -> FakeChaos:
    return FakeChaos()


@pytest.fixture
def client(
    db_session: Session,
    kubernetes: FakeKubernetes,
    prometheus: FakePrometheus,
    chaos: FakeChaos,
) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_kubernetes_adapter] = lambda: kubernetes
    app.dependency_overrides[get_prometheus_client] = lambda: prometheus
    app.dependency_overrides[get_baseline_window_seconds] = lambda: WINDOW_SECONDS
    app.dependency_overrides[get_chaos_provider] = lambda: chaos
    app.dependency_overrides[get_start_wait] = lambda: FAST_WAIT
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
