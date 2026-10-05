from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.experiments import get_kubernetes_adapter
from app.db import models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base
from app.db.session import get_db
from app.domain.experiment import ExperimentTarget
from app.integrations.kubernetes_adapter import ClusterUnavailableError, WorkloadStatus
from app.main import app


class FakeKubernetes:
    """Stands in for KubernetesAdapter; defaults to a healthy 3-replica workload."""

    def __init__(self) -> None:
        self.status: WorkloadStatus | None = WorkloadStatus(3, 3, 3)
        self.error: str | None = None
        self.calls: list[ExperimentTarget] = []

    def get_workload_status(self, target: ExperimentTarget) -> WorkloadStatus | None:
        self.calls.append(target)
        if self.error is not None:
            raise ClusterUnavailableError(self.error)
        return self.status


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
def client(db_session: Session, kubernetes: FakeKubernetes) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_kubernetes_adapter] = lambda: kubernetes
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
