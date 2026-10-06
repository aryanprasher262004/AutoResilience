"""GET /services and GET /services/{namespace}/{kind}/{name} (read-only discovery)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.experiment import PodDeleteMode, WorkloadKind
from app.domain.state_machine import ExperimentState as S
from app.integrations.kubernetes_adapter import WorkloadStatus, WorkloadSummary
from tests.api.test_history import add, observation, score
from tests.conftest import FakeKubernetes

D, SS = WorkloadKind.DEPLOYMENT, WorkloadKind.STATEFULSET
CREATED = datetime(2026, 10, 1, tzinfo=UTC)


def workload(
    namespace: str,
    name: str,
    desired: int,
    ready: int,
    kind: WorkloadKind = D,
) -> WorkloadSummary:
    return WorkloadSummary(
        namespace, kind, name, desired, desired, ready, ready, CREATED
    )


@pytest.fixture
def cluster(kubernetes: FakeKubernetes) -> FakeKubernetes:
    kubernetes.workloads = [
        workload("shop", "frontend", 3, 3),
        workload("shop", "checkout", 2, 1),
        workload("shop", "cart-redis", 1, 1, SS),
        workload("shop", "idle", 0, 0),
        workload("resilience-sandbox", "fragile", 1, 0),
        workload("kube-system", "coredns", 2, 2),
        workload("local-path-storage", "local-path-provisioner", 1, 1),
        workload("litmus", "litmus", 1, 1),
        workload("monitoring", "prometheus-server", 1, 1),
    ]
    return kubernetes


def test_lists_workloads_outside_system_namespaces(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    body = client.get("/services").json()

    names = [(i["namespace"], i["kind"], i["name"]) for i in body["items"]]
    assert names == [
        ("resilience-sandbox", "Deployment", "fragile"),
        ("shop", "StatefulSet", "cart-redis"),
        ("shop", "Deployment", "checkout"),
        ("shop", "Deployment", "frontend"),
        ("shop", "Deployment", "idle"),
    ]
    assert "local-path-storage" in body["excluded_namespaces"]
    assert "kube-system" in body["excluded_namespaces"]


def test_health_from_desired_and_ready(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    items = {i["name"]: i for i in client.get("/services").json()["items"]}

    assert items["frontend"]["health"] == "HEALTHY"
    assert items["checkout"]["health"] == "DEGRADED"
    assert items["fragile"]["health"] == "UNAVAILABLE"
    assert items["idle"]["health"] == "SCALED_TO_ZERO"
    assert (
        items["checkout"]["desired_replicas"],
        items["checkout"]["ready_replicas"],
    ) == (2, 1)


def test_history_is_matched_on_the_exact_target(
    client: TestClient, cluster: FakeKubernetes, db_session: Session
) -> None:
    add(db_session, "old", S.COMPLETED, minutes=0, score=score(70.0, version="v2"))
    add(
        db_session,
        "scored",
        S.COMPLETED,
        minutes=1,
        score=score(88.5),
        observation=observation(4.0, 3.0),
    )
    add(db_session, "newest", S.VALIDATION_FAILED, minutes=2)
    add(
        db_session,
        "other ns",
        S.COMPLETED,
        minutes=3,
        namespace="resilience-sandbox",
        score=score(50.0),
    )  # resilience-sandbox/checkout: not a cluster workload

    items = {i["name"]: i for i in client.get("/services").json()["items"]}

    checkout = items["checkout"]
    assert checkout["experiment_count"] == 3
    assert checkout["latest_experiment"]["name"] == "newest"
    assert checkout["latest_score"]["score"] == 88.5
    assert checkout["latest_score"]["version"] == "v3"
    assert items["frontend"]["experiment_count"] == 0
    assert items["frontend"]["latest_experiment"] is None
    assert items["frontend"]["latest_score"] is None
    assert items["fragile"]["experiment_count"] == 0


def test_cluster_unavailable_is_503(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    cluster.error = "Kubernetes API unreachable: connection refused"

    response = client.get("/services")

    assert response.status_code == 503
    assert response.json()["detail"] == "Kubernetes API unreachable: connection refused"


def test_detail_combines_live_status_and_history(
    client: TestClient, kubernetes: FakeKubernetes, db_session: Session
) -> None:
    kubernetes.status = WorkloadStatus(2, 2, 1, ready_pod_names=("checkout-a",))
    add(db_session, "g1", S.COMPLETED, minutes=0, score=score(80.0))
    add(
        db_session,
        "f1",
        S.COMPLETED,
        minutes=1,
        mode=PodDeleteMode.FORCE,
        score=score(76.8, version="v2"),
    )
    add(db_session, "g2", S.COMPLETED, minutes=2, score=score(91.0, rating="Excellent"))
    add(db_session, "g3", S.ABORTED, minutes=3)

    body = client.get("/services/shop/Deployment/checkout").json()

    assert body["health"] == "DEGRADED"
    assert body["live"] == {
        "desired_replicas": 2,
        "running_pods": 2,
        "ready_pods": 1,
        "ready_pod_names": ["checkout-a"],
    }
    assert body["experiment_count"] == 4
    assert [e["name"] for e in body["experiments"]] == ["g3", "g2", "f1", "g1"]
    assert body["latest_score"]["score"] == 91.0
    faults = {f["pod_delete_mode"]: f for f in body["faults"]}
    assert (faults["GRACEFUL"]["runs"], faults["GRACEFUL"]["completed"]) == (3, 2)
    assert faults["GRACEFUL"]["latest_score"]["score"] == 91.0
    assert faults["FORCE"]["latest_score"]["version"] == "v2"
    # Trend: current methodology only, oldest first.
    assert [p["score"] for p in body["score_history"]] == [80.0, 91.0]
    assert body["score_version"] == "v3"
    assert kubernetes.calls[-1].name == "checkout"


def test_detail_without_history(client: TestClient, kubernetes: FakeKubernetes) -> None:
    body = client.get("/services/shop/Deployment/frontend").json()

    assert body["health"] == "HEALTHY"
    assert body["experiment_count"] == 0
    assert body["experiments"] == body["faults"] == body["score_history"] == []
    assert body["latest_score"] is None


def test_detail_of_deleted_workload_keeps_history(
    client: TestClient, kubernetes: FakeKubernetes, db_session: Session
) -> None:
    kubernetes.status = None
    add(db_session, "g1", S.COMPLETED, minutes=0)

    body = client.get("/services/shop/Deployment/checkout").json()

    assert body["health"] == "NOT_FOUND"
    assert body["live"] is None
    assert body["experiment_count"] == 1


def test_detail_unknown_workload_is_404(
    client: TestClient, kubernetes: FakeKubernetes
) -> None:
    kubernetes.status = None
    assert client.get("/services/shop/Deployment/nope").status_code == 404


def test_detail_cluster_error_still_returns_history(
    client: TestClient, kubernetes: FakeKubernetes, db_session: Session
) -> None:
    kubernetes.error = "Kubernetes API error 500: boom"
    add(db_session, "g1", S.COMPLETED, minutes=0)

    body = client.get("/services/shop/Deployment/checkout").json()

    assert body["health"] == "UNKNOWN"
    assert body["cluster_error"] == "Kubernetes API error 500: boom"
    assert body["experiment_count"] == 1


@pytest.mark.parametrize("namespace", ["kube-system", "local-path-storage", "litmus"])
def test_detail_refuses_system_namespaces(
    client: TestClient, kubernetes: FakeKubernetes, namespace: str
) -> None:
    response = client.get(f"/services/{namespace}/Deployment/x")

    assert response.status_code == 404
    assert kubernetes.calls == []


def test_detail_rejects_unknown_kind(client: TestClient) -> None:
    assert client.get("/services/shop/DaemonSet/x").status_code == 422
