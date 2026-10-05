import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.experiments import get_safety_policy
from app.db.models import Experiment
from app.domain.safety_policy import SafetyPolicy
from app.integrations.kubernetes_adapter import WorkloadStatus
from app.main import app
from tests.api.test_experiments import payload
from tests.conftest import FakeKubernetes


def create(client: TestClient, **overrides: Any) -> str:
    response = client.post("/experiments", json=payload(**overrides))
    assert response.status_code == 201
    experiment_id: str = response.json()["id"]
    return experiment_id


def validate(client: TestClient, experiment_id: str) -> dict[str, Any]:
    response = client.post(f"/experiments/{experiment_id}/validate")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def statuses(body: dict[str, Any], group: str) -> dict[str, str]:
    return {c["name"]: c["status"] for c in body["validation_result"][group]}


def failed_checks(body: dict[str, Any]) -> set[str]:
    result = body["validation_result"]
    checks = result["static_checks"] + result["cluster_checks"]
    return {c["name"] for c in checks if c["status"] != "PASSED"}


def test_valid_experiment_moves_to_baselining_and_persists(
    client: TestClient, db_session: Session
) -> None:
    experiment_id = create(client)

    body = validate(client, experiment_id)

    assert body["state"] == "BASELINING"
    result = body["validation_result"]
    assert result["passed"] is True
    assert set(statuses(body, "static_checks").values()) == {"PASSED"}
    assert statuses(body, "cluster_checks") == {
        "target_workload_exists": "PASSED",
        "target_has_running_pods": "PASSED",
        "min_healthy_replicas_after_fault": "PASSED",
    }
    assert result["policy"]["max_duration_seconds"] == 300
    assert result["policy"]["min_healthy_replicas"] == 1

    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None
    assert stored.state == "BASELINING"
    assert stored.validation_result == result
    assert client.get(f"/experiments/{experiment_id}").json() == body


@pytest.mark.parametrize(
    ("overrides", "expected_failure"),
    [
        (
            {
                "target": {
                    "namespace": "kube-system",
                    "kind": "Deployment",
                    "name": "dns",
                }
            },
            "namespace_not_forbidden",
        ),
        ({"duration_seconds": 301}, "duration_within_limit"),
        ({"affected_replicas": 2}, "affected_replicas_within_limit"),
    ],
)
def test_policy_violation_moves_to_validation_failed(
    client: TestClient,
    db_session: Session,
    kubernetes: FakeKubernetes,
    overrides: dict[str, Any],
    expected_failure: str,
) -> None:
    experiment_id = create(client, **overrides)

    body = validate(client, experiment_id)

    assert body["state"] == "VALIDATION_FAILED"
    assert body["validation_result"]["passed"] is False
    failed_static = {
        k for k, v in statuses(body, "static_checks").items() if v != "PASSED"
    }
    assert failed_static == {expected_failure}
    # Static failure means the cluster is never queried.
    assert set(statuses(body, "cluster_checks").values()) == {"SKIPPED"}
    assert kubernetes.calls == []
    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None
    assert stored.state == "VALIDATION_FAILED"


def test_all_violations_are_reported_together(client: TestClient) -> None:
    experiment_id = create(
        client,
        target={"namespace": "monitoring", "kind": "StatefulSet", "name": "prometheus"},
        duration_seconds=900,
        affected_replicas=3,
    )

    body = validate(client, experiment_id)

    failed_static = {
        k for k, v in statuses(body, "static_checks").items() if v != "PASSED"
    }
    assert failed_static == {
        "namespace_not_forbidden",
        "duration_within_limit",
        "affected_replicas_within_limit",
    }
    messages = [c["message"] for c in body["validation_result"]["static_checks"]]
    assert "Duration 900s > limit 300s" in messages


@pytest.fixture
def allowlist_policy(client: TestClient) -> Iterator[None]:
    app.dependency_overrides[get_safety_policy] = lambda: SafetyPolicy(
        allowed_namespaces=frozenset({"sandbox"})
    )
    yield
    app.dependency_overrides.pop(get_safety_policy, None)


@pytest.mark.usefixtures("allowlist_policy")
def test_namespace_outside_allowlist_fails(client: TestClient) -> None:
    body = validate(client, create(client))

    assert body["state"] == "VALIDATION_FAILED"
    assert statuses(body, "static_checks")["namespace_allowed"] == "FAILED"


@pytest.mark.usefixtures("allowlist_policy")
def test_namespace_in_allowlist_passes(client: TestClient) -> None:
    target = {"namespace": "sandbox", "kind": "Deployment", "name": "checkout"}
    body = validate(client, create(client, target=target))

    assert body["state"] == "BASELINING"


@pytest.mark.parametrize("first_outcome_overrides", [{}, {"duration_seconds": 999}])
def test_revalidation_is_rejected_by_state_machine(
    client: TestClient, first_outcome_overrides: dict[str, Any]
) -> None:
    experiment_id = create(client, **first_outcome_overrides)
    first = validate(client, experiment_id)

    response = client.post(f"/experiments/{experiment_id}/validate")

    assert response.status_code == 409
    assert "Invalid experiment state transition" in response.json()["detail"]
    assert client.get(f"/experiments/{experiment_id}").json() == first


def test_validate_unknown_experiment_returns_404(client: TestClient) -> None:
    response = client.post(f"/experiments/{uuid.uuid4()}/validate")
    assert response.status_code == 404


def test_missing_workload_fails_cluster_check(
    client: TestClient, kubernetes: FakeKubernetes
) -> None:
    kubernetes.status = None

    body = validate(client, create(client))

    assert body["state"] == "VALIDATION_FAILED"
    assert statuses(body, "cluster_checks") == {
        "target_workload_exists": "FAILED",
        "target_has_running_pods": "SKIPPED",
        "min_healthy_replicas_after_fault": "SKIPPED",
    }
    assert kubernetes.calls[0].name == "checkout"


def test_workload_without_ready_pods_fails(
    client: TestClient, kubernetes: FakeKubernetes
) -> None:
    kubernetes.status = WorkloadStatus(desired_replicas=2, running_pods=1, ready_pods=0)

    body = validate(client, create(client))

    assert body["state"] == "VALIDATION_FAILED"
    assert statuses(body, "cluster_checks")["target_has_running_pods"] == "FAILED"


def test_blast_radius_leaving_too_few_healthy_replicas_fails(
    client: TestClient, kubernetes: FakeKubernetes
) -> None:
    kubernetes.status = WorkloadStatus(desired_replicas=1, running_pods=1, ready_pods=1)

    body = validate(client, create(client))

    assert body["state"] == "VALIDATION_FAILED"
    assert failed_checks(body) == {"min_healthy_replicas_after_fault"}
    check = body["validation_result"]["cluster_checks"][2]
    assert check["message"] == "1 ready - 1 affected = 0 remaining < minimum 1"


def test_cluster_unavailable_is_error_not_pass(
    client: TestClient, db_session: Session, kubernetes: FakeKubernetes
) -> None:
    kubernetes.error = "Kubernetes API unreachable: connection refused"

    body = validate(client, create(client))

    assert body["state"] == "VALIDATION_FAILED"
    assert set(statuses(body, "cluster_checks").values()) == {"ERROR"}
    assert (
        "connection refused"
        in body["validation_result"]["cluster_checks"][0]["message"]
    )
    stored = db_session.get(Experiment, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.state == "VALIDATION_FAILED"
