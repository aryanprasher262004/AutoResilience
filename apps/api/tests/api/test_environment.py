"""GET /environment: database, cluster and Prometheus as the API itself sees them."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.services.readiness import migration_head
from tests.conftest import FakeKubernetes, FakePrometheus


@pytest.fixture
def settings() -> Iterator[Settings]:
    value = Settings(
        runtime_mode="local-stack",
        kube_context="kind-autoresilience",
        prometheus_url="http://user:secret@autoresilience-control-plane:30090/",
    )
    app.dependency_overrides[get_settings] = lambda: value
    yield value
    app.dependency_overrides.pop(get_settings, None)


def migrated(db: Session) -> None:
    db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    db.execute(text("INSERT INTO alembic_version VALUES (:r)"), {"r": migration_head()})
    db.commit()


def test_reports_every_dependency_when_healthy(
    client: TestClient, db_session: Session, settings: Settings
) -> None:
    migrated(db_session)

    body = client.get("/environment").json()

    assert body["runtime_mode"] == "local-stack"
    assert body["kube_context"] == "kind-autoresilience"
    # Credentials in the configured URL are never echoed.
    assert body["prometheus_url"] == "http://autoresilience-control-plane:30090"
    assert {c["name"]: c["status"] for c in body["checks"]} == {
        "database": "pass",
        "kubernetes": "pass",
        "prometheus": "pass",
    }
    kube = next(c for c in body["checks"] if c["name"] == "kubernetes")
    assert kube["detail"] == "0 workloads visible via context kind-autoresilience"


def test_failures_are_reported_per_check_with_status_200(
    client: TestClient,
    settings: Settings,
    kubernetes: FakeKubernetes,
    prometheus: FakePrometheus,
) -> None:
    kubernetes.error = "Kubernetes API error 403: Forbidden"
    prometheus.error = "Prometheus unreachable: ConnectError()"

    response = client.get("/environment")

    assert response.status_code == 200
    checks = {c["name"]: c for c in response.json()["checks"]}
    assert checks["database"]["status"] == "fail"  # schema not migrated
    assert checks["kubernetes"] == {
        "name": "kubernetes",
        "status": "fail",
        "detail": "Cannot list workloads via context kind-autoresilience: "
        "Kubernetes API error 403: Forbidden",
    }
    assert checks["prometheus"]["status"] == "fail"
    assert "secret" not in response.text


def test_development_mode_names_the_current_context_fallback(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(kube_context=None)
    try:
        body = client.get("/environment").json()
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert body["runtime_mode"] == "development"
    assert body["kube_context"] is None
    kube = next(c for c in body["checks"] if c["name"] == "kubernetes")
    assert "the kubeconfig's current context" in kube["detail"]
