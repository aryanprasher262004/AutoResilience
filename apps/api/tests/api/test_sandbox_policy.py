import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.experiment import ExperimentTarget, WorkloadKind
from app.integrations.kubernetes_adapter import WorkloadStatus
from tests.api.test_experiments import payload
from tests.conftest import FakeChaos, FakeKubernetes, FakePrometheus

SANDBOX_TARGET = {
    "namespace": "resilience-sandbox",
    "kind": "Deployment",
    "name": "fragile",
}
SHOP_SINGLE = {"namespace": "shop", "kind": "Deployment", "name": "checkout"}


@pytest.fixture
def prometheus() -> FakePrometheus:
    # Baseline queries are keyed to the target, so answer for the sandbox workload.
    return FakePrometheus(
        target=ExperimentTarget(
            "resilience-sandbox", WorkloadKind.DEPLOYMENT, "fragile"
        )
    )


@pytest.fixture
def single_replica(kubernetes: FakeKubernetes) -> None:
    kubernetes.status = WorkloadStatus(
        1, 1, 1, selector="app=fragile", ready_pod_names=("fragile-abc-12345",)
    )


def validate(client: TestClient, **overrides: Any) -> dict[str, Any]:
    experiment_id = client.post("/experiments", json=payload(**overrides)).json()["id"]
    body: dict[str, Any] = client.post(f"/experiments/{experiment_id}/validate").json()
    return body


def cluster(body: dict[str, Any]) -> dict[str, str]:
    return {c["name"]: c["status"] for c in body["validation_result"]["cluster_checks"]}


@pytest.mark.usefixtures("single_replica")
def test_single_replica_in_shop_is_still_blocked(client: TestClient) -> None:
    body = validate(client, target=SHOP_SINGLE)

    assert body["state"] == "VALIDATION_FAILED"
    assert cluster(body)["min_healthy_replicas_after_fault"] == "FAILED"
    result = body["validation_result"]
    assert result["policy"]["name"] == "default"
    assert result["policy"]["min_healthy_replicas"] == 1
    assert result["policy_selection"] == {
        "namespace": "shop",
        "policy": "default",
        "rule": "no namespace-specific policy; default applies",
    }


@pytest.mark.usefixtures("single_replica")
def test_single_replica_in_sandbox_passes_with_auditable_policy(
    client: TestClient, db_session: Session
) -> None:
    body = validate(client, target=SANDBOX_TARGET)

    assert body["state"] == "BASELINING"
    assert set(cluster(body).values()) == {"PASSED"}
    result = body["validation_result"]
    assert result["policy"]["name"] == "sandbox"
    assert result["policy"]["min_healthy_replicas"] == 0
    assert result["policy"]["allowed_namespaces"] == ["resilience-sandbox"]
    assert result["policy_selection"]["rule"] == (
        "namespace 'resilience-sandbox' maps to policy 'sandbox'"
    )
    stored = db_session.get(Experiment, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.validation_result is not None
    assert stored.validation_result["policy"]["name"] == "sandbox"


@pytest.mark.usefixtures("single_replica")
@pytest.mark.parametrize(
    "spoof",
    [
        {"policy": "sandbox"},
        {"safety_policy": {"min_healthy_replicas": 0}},
        {"policy_name": "sandbox", "min_healthy_replicas": 0},
        {"policy_selection": {"namespace": "resilience-sandbox", "policy": "sandbox"}},
    ],
)
def test_policy_cannot_be_chosen_by_request_fields(
    client: TestClient, spoof: dict[str, Any]
) -> None:
    body = validate(client, target=SHOP_SINGLE, **spoof)

    assert body["state"] == "VALIDATION_FAILED"
    assert body["validation_result"]["policy"]["name"] == "default"


def test_kube_system_forbidden_and_cluster_not_queried(
    client: TestClient, kubernetes: FakeKubernetes
) -> None:
    body = validate(
        client,
        target={"namespace": "kube-system", "kind": "Deployment", "name": "coredns"},
    )

    assert body["state"] == "VALIDATION_FAILED"
    static = {
        c["name"]: c["status"] for c in body["validation_result"]["static_checks"]
    }
    assert static["namespace_not_forbidden"] == "FAILED"
    assert kubernetes.calls == []


@pytest.mark.usefixtures("single_replica")
def test_sandbox_experiment_injects_and_records_policy(
    client: TestClient, chaos: FakeChaos
) -> None:
    experiment_id = validate(client, target=SANDBOX_TARGET)["id"]
    assert client.post(f"/experiments/{experiment_id}/baseline").json()["state"] == (
        "INJECTING"
    )

    body = client.post(f"/experiments/{experiment_id}/inject").json()

    assert body["state"] == "OBSERVING"
    assert body["chaos"]["safety_policy"] == "sandbox"
    assert chaos.requests[0].target_pods == ("fragile-abc-12345",)


@pytest.mark.usefixtures("single_replica")
def test_injection_refuses_if_policy_changed_since_validation(
    client: TestClient, db_session: Session, chaos: FakeChaos
) -> None:
    experiment_id = validate(client, target=SANDBOX_TARGET)["id"]
    client.post(f"/experiments/{experiment_id}/baseline")
    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None and stored.validation_result is not None
    tampered = dict(stored.validation_result)
    tampered["policy"] = {**tampered["policy"], "name": "default"}
    stored.validation_result = tampered
    db_session.commit()

    body = client.post(f"/experiments/{experiment_id}/inject").json()

    assert body["state"] == "INJECTION_FAILED"
    assert "policy changed since validation" in body["chaos"]["failure_reason"]
    assert chaos.requests == []


def test_shop_three_replicas_unchanged(client: TestClient) -> None:
    body = validate(client)
    assert body["state"] == "BASELINING"
    assert body["validation_result"]["policy"]["name"] == "default"
