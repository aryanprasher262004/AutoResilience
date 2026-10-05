import uuid
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Experiment
from tests.api.test_experiments import payload
from tests.conftest import FakePrometheus


def validated_experiment(client: TestClient, **overrides: Any) -> str:
    experiment_id: str = client.post("/experiments", json=payload(**overrides)).json()[
        "id"
    ]
    assert client.post(f"/experiments/{experiment_id}/validate").json()["state"] == (
        "BASELINING"
    )
    return experiment_id


def baseline(client: TestClient, experiment_id: str) -> dict[str, Any]:
    response = client.post(f"/experiments/{experiment_id}/baseline")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_successful_baseline_moves_to_injecting_and_persists(
    client: TestClient, db_session: Session
) -> None:
    experiment_id = validated_experiment(client)

    body = baseline(client, experiment_id)

    assert body["state"] == "INJECTING"
    assert body["baseline"]["status"] == "CAPTURED"
    assert body["baseline"]["availability"]["values"]["availability_ratio"] == 1.0
    assert body["baseline"]["requests"]["values"]["request_rate_rps"] == 1.5
    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None
    assert stored.state == "INJECTING"
    assert stored.baseline is not None
    stored_baseline, api_baseline = dict(stored.baseline), dict(body["baseline"])
    assert datetime.fromisoformat(stored_baseline.pop("captured_at")) == (
        datetime.fromisoformat(api_baseline.pop("captured_at"))
    )
    assert stored_baseline == api_baseline
    reread = client.get(f"/experiments/{experiment_id}").json()
    assert reread["state"] == "INJECTING"
    assert reread["baseline"]["status"] == "CAPTURED"


def test_failed_baseline_stays_in_baselining_with_reason(
    client: TestClient, db_session: Session, prometheus: FakePrometheus
) -> None:
    experiment_id = validated_experiment(client)
    prometheus.error = "Prometheus unreachable: connection refused"

    body = baseline(client, experiment_id)

    assert body["state"] == "BASELINING"
    assert body["baseline"]["status"] == "FAILED"
    assert "connection refused" in body["baseline"]["failure_reasons"][0]
    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None
    assert stored.state == "BASELINING"
    assert stored.baseline is not None
    assert stored.baseline["status"] == "FAILED"


def test_failed_baseline_can_be_retried(
    client: TestClient, prometheus: FakePrometheus
) -> None:
    experiment_id = validated_experiment(client)
    prometheus.values["availability_samples"] = 1
    assert baseline(client, experiment_id)["state"] == "BASELINING"

    prometheus.values["availability_samples"] = 20
    body = baseline(client, experiment_id)

    assert body["state"] == "INJECTING"
    assert body["baseline"]["status"] == "CAPTURED"


def test_target_without_request_metrics_still_reaches_injecting(
    client: TestClient, prometheus: FakePrometheus
) -> None:
    experiment_id = validated_experiment(client)
    prometheus.values["request_series"] = None

    body = baseline(client, experiment_id)

    assert body["state"] == "INJECTING"
    assert body["baseline"]["requests"]["status"] == "UNAVAILABLE"


def test_baseline_requires_baselining_state(
    client: TestClient, prometheus: FakePrometheus
) -> None:
    created = client.post("/experiments", json=payload()).json()

    response = client.post(f"/experiments/{created['id']}/baseline")

    assert response.status_code == 409
    assert "CREATED -> INJECTING" in response.json()["detail"]
    assert prometheus.queries == []  # nothing queried before the state check
    assert client.get(f"/experiments/{created['id']}").json()["baseline"] is None


@pytest.mark.parametrize("overrides", [{}, {"duration_seconds": 999}])
def test_baseline_rejected_after_injecting_or_validation_failure(
    client: TestClient, overrides: dict[str, Any]
) -> None:
    experiment_id = client.post("/experiments", json=payload(**overrides)).json()["id"]
    client.post(f"/experiments/{experiment_id}/validate")
    if not overrides:
        assert baseline(client, experiment_id)["state"] == "INJECTING"

    response = client.post(f"/experiments/{experiment_id}/baseline")

    assert response.status_code == 409


def test_baseline_unknown_experiment_returns_404(client: TestClient) -> None:
    assert client.post(f"/experiments/{uuid.uuid4()}/baseline").status_code == 404
