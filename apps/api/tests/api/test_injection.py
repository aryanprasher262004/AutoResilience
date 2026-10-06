import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.experiments import get_policy_resolver
from app.db.models import Experiment
from app.domain.safety_policy import SafetyPolicy
from app.domain.state_machine import ExperimentState
from app.integrations.chaos_provider import ChaosProviderError, FaultPhase
from app.integrations.kubernetes_adapter import ClusterUnavailableError, WorkloadStatus
from app.main import app
from tests.api.test_experiments import payload
from tests.conftest import FakeChaos, FakeKubernetes, FakePrometheus, fault


def ready_to_inject(client: TestClient, **overrides: Any) -> str:
    experiment_id: str = client.post("/experiments", json=payload(**overrides)).json()[
        "id"
    ]
    assert client.post(f"/experiments/{experiment_id}/validate").json()["state"] == (
        "BASELINING"
    )
    assert client.post(f"/experiments/{experiment_id}/baseline").json()["state"] == (
        "INJECTING"
    )
    return experiment_id


def inject(client: TestClient, experiment_id: str) -> dict[str, Any]:
    response = client.post(f"/experiments/{experiment_id}/inject")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_successful_injection_moves_to_observing_and_persists(
    client: TestClient,
    db_session: Session,
    chaos: FakeChaos,
    kubernetes: FakeKubernetes,
) -> None:
    experiment_id = ready_to_inject(client)

    body = inject(client, experiment_id)

    assert body["state"] == "OBSERVING"
    record = body["chaos"]
    assert record["engine_name"] == f"ar-{experiment_id}"
    assert record["namespace"] == "shop"
    assert record["target_pods"] == ["checkout-a"]
    assert record["duration_seconds"] == 60
    assert record["injected_at"] is not None
    assert record["status"]["phase"] == "RUNNING"
    assert record["failure_reason"] is None
    (request,) = chaos.requests
    assert request.target.name == "checkout"
    assert request.label_selector == "app=checkout"
    assert request.target_pods == ("checkout-a",)
    assert request.duration_seconds == 60
    assert kubernetes.live_calls == [["checkout-a"]]
    assert chaos.stopped == []
    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None
    assert stored.state == "OBSERVING"
    assert stored.chaos is not None
    assert stored.chaos["engine_name"] == record["engine_name"]


def test_affected_replicas_selects_first_n_ready_pods(
    client: TestClient, chaos: FakeChaos
) -> None:
    app.dependency_overrides[get_policy_resolver] = lambda: (
        lambda _ns: SafetyPolicy(max_affected_replicas=2)
    )
    body = inject(client, ready_to_inject(client, affected_replicas=2))

    assert body["state"] == "OBSERVING"
    assert chaos.requests[0].target_pods == ("checkout-a", "checkout-b")


def test_waits_until_target_pods_are_actually_gone(
    client: TestClient, chaos: FakeChaos, kubernetes: FakeKubernetes
) -> None:
    chaos.statuses = [fault(FaultPhase.RUNNING)]
    kubernetes.live_sequence = [{"checkout-a"}, {"checkout-a"}, set()]

    body = inject(client, ready_to_inject(client))

    assert body["state"] == "OBSERVING"
    assert len(kubernetes.live_calls) == 3


def test_litmus_failure_moves_to_injection_failed_and_stops_engine(
    client: TestClient, chaos: FakeChaos
) -> None:
    chaos.statuses = [fault(FaultPhase.PENDING), fault(FaultPhase.FAILED, "Fail")]
    experiment_id = ready_to_inject(client)

    body = inject(client, experiment_id)

    assert body["state"] == "INJECTION_FAILED"
    assert "Litmus reported failure" in body["chaos"]["failure_reason"]
    assert "verdict=Fail" in body["chaos"]["failure_reason"]
    assert chaos.stopped == [("shop", f"ar-{experiment_id}")]
    assert body["chaos"]["stopped"] is True


def test_timeout_without_deletion_fails_and_stops_engine(
    client: TestClient, chaos: FakeChaos
) -> None:
    chaos.statuses = [fault(FaultPhase.PENDING)]

    body = inject(client, ready_to_inject(client))

    assert body["state"] == "INJECTION_FAILED"
    assert "not deleted within 10s" in body["chaos"]["failure_reason"]
    assert chaos.status_calls == 10
    assert len(chaos.stopped) == 1


def test_completed_but_pods_still_alive_fails(
    client: TestClient, chaos: FakeChaos, kubernetes: FakeKubernetes
) -> None:
    chaos.statuses = [fault(FaultPhase.COMPLETED, "Pass")]
    kubernetes.live_sequence = [{"checkout-a"}]

    body = inject(client, ready_to_inject(client))

    assert body["state"] == "INJECTION_FAILED"
    assert "still exist" in body["chaos"]["failure_reason"]


def test_engine_creation_error_fails_without_engine(
    client: TestClient, chaos: FakeChaos
) -> None:
    chaos.start_error = "Failed to create ChaosEngine: Kubernetes API error 403"

    body = inject(client, ready_to_inject(client))

    assert body["state"] == "INJECTION_FAILED"
    assert body["chaos"]["engine_name"] is None
    assert "403" in body["chaos"]["failure_reason"]
    assert chaos.stopped == []


def test_status_read_error_fails_and_records_stop_error(
    client: TestClient, chaos: FakeChaos
) -> None:
    chaos.statuses = [ChaosProviderError("Failed to read ChaosEngine: 500")]
    chaos.stop_error = "Failed to stop ChaosEngine: unreachable"

    body = inject(client, ready_to_inject(client))

    assert body["state"] == "INJECTION_FAILED"
    assert body["chaos"]["stopped"] is False
    assert "unreachable" in body["chaos"]["stop_error"]


def test_deletion_check_error_fails(
    client: TestClient, chaos: FakeChaos, kubernetes: FakeKubernetes
) -> None:
    kubernetes.live_sequence = [ClusterUnavailableError("connection refused")]

    body = inject(client, ready_to_inject(client))

    assert body["state"] == "INJECTION_FAILED"
    assert "Could not confirm pod deletion" in body["chaos"]["failure_reason"]
    assert len(chaos.stopped) == 1


def test_cluster_changed_since_validation_blocks_injection(
    client: TestClient, chaos: FakeChaos, kubernetes: FakeKubernetes
) -> None:
    experiment_id = ready_to_inject(client)
    # Two replicas went away after validation: 1 ready - 1 affected = 0 < min 1.
    kubernetes.status = WorkloadStatus(
        3, 1, 1, selector="app=checkout", ready_pod_names=("checkout-c",)
    )

    body = inject(client, experiment_id)

    assert body["state"] == "INJECTION_FAILED"
    assert "Pre-injection cluster check failed" in body["chaos"]["failure_reason"]
    assert "0 remaining < minimum 1" in body["chaos"]["failure_reason"]
    assert chaos.requests == []


def test_cluster_unreachable_before_injection_blocks_it(
    client: TestClient, chaos: FakeChaos, kubernetes: FakeKubernetes
) -> None:
    experiment_id = ready_to_inject(client)
    kubernetes.error = "Kubernetes API unreachable"

    body = inject(client, experiment_id)

    assert body["state"] == "INJECTION_FAILED"
    assert chaos.requests == []


@pytest.mark.parametrize("field", ["validation_result", "baseline"])
def test_missing_preconditions_block_injection(
    client: TestClient, db_session: Session, chaos: FakeChaos, field: str
) -> None:
    experiment_id = ready_to_inject(client)
    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None
    setattr(stored, field, None)
    db_session.commit()

    body = inject(client, experiment_id)

    assert body["state"] == "INJECTION_FAILED"
    assert chaos.requests == []


def test_inject_requires_injecting_state(client: TestClient, chaos: FakeChaos) -> None:
    created = client.post("/experiments", json=payload()).json()
    client.post(f"/experiments/{created['id']}/validate")  # -> BASELINING

    response = client.post(f"/experiments/{created['id']}/inject")

    assert response.status_code == 409
    assert "BASELINING -> OBSERVING" in response.json()["detail"]
    assert chaos.requests == []


def test_cannot_inject_twice(client: TestClient, chaos: FakeChaos) -> None:
    experiment_id = ready_to_inject(client)
    assert inject(client, experiment_id)["state"] == "OBSERVING"

    assert client.post(f"/experiments/{experiment_id}/inject").status_code == 409
    assert len(chaos.requests) == 1


def test_failed_baseline_never_reaches_injection(
    client: TestClient, chaos: FakeChaos, prometheus: FakePrometheus
) -> None:
    experiment_id = client.post("/experiments", json=payload()).json()["id"]
    client.post(f"/experiments/{experiment_id}/validate")
    prometheus.error = "down"
    assert client.post(f"/experiments/{experiment_id}/baseline").json()["state"] == (
        ExperimentState.BASELINING
    )

    assert client.post(f"/experiments/{experiment_id}/inject").status_code == 409
    assert chaos.requests == []


def test_unsupported_fault_type_fails_validation(
    client: TestClient, chaos: FakeChaos
) -> None:
    experiment_id = client.post(
        "/experiments", json=payload(fault_type="pod-cpu-hog")
    ).json()["id"]

    body = client.post(f"/experiments/{experiment_id}/validate").json()

    assert body["state"] == "VALIDATION_FAILED"
    static = {
        c["name"]: c["status"] for c in body["validation_result"]["static_checks"]
    }
    assert static["fault_type_supported"] == "FAILED"


def test_inject_unknown_experiment_returns_404(client: TestClient) -> None:
    assert client.post(f"/experiments/{uuid.uuid4()}/inject").status_code == 404
