import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.experiment import PodDeleteMode
from tests.api.test_experiments import payload
from tests.api.test_observation import COMPLETED_PASS, observe
from tests.conftest import Clock, FakeChaos, FakePrometheus


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/experiments", json=payload(**overrides))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_mode_defaults_to_graceful(client: TestClient, db_session: Session) -> None:
    body = create(client)

    assert body["pod_delete_mode"] == "GRACEFUL"
    stored = db_session.get(Experiment, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.pod_delete_mode is PodDeleteMode.GRACEFUL


@pytest.mark.parametrize("mode", ["GRACEFUL", "FORCE"])
def test_mode_is_persisted(client: TestClient, db_session: Session, mode: str) -> None:
    body = create(client, pod_delete_mode=mode)

    assert body["pod_delete_mode"] == mode
    assert client.get(f"/experiments/{body['id']}").json()["pod_delete_mode"] == mode
    stored = db_session.get(Experiment, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.pod_delete_mode == mode


@pytest.mark.parametrize(
    "mode",
    ["force", "Force", "SIGKILL", "", None, 0, "GRACEFUL;FORCE", {"FORCE": True}],
)
def test_invalid_mode_is_rejected_and_not_persisted(
    client: TestClient, db_session: Session, mode: Any
) -> None:
    response = client.post("/experiments", json=payload(pod_delete_mode=mode))

    assert response.status_code == 422
    assert db_session.query(Experiment).count() == 0


def test_arbitrary_litmus_options_are_ignored_not_forwarded(
    client: TestClient, chaos: FakeChaos
) -> None:
    """Unknown fields (e.g. raw Litmus env) never reach the provider."""
    body = create(
        client,
        pod_delete_mode="FORCE",
        litmus_env={"FORCE": "false", "TARGET_PODS": "everything"},
    )
    assert "litmus_env" not in body


def run_to_observing(client: TestClient, mode: str) -> tuple[str, dict[str, Any]]:
    experiment_id = create(client, pod_delete_mode=mode)["id"]
    for step in ("validate", "baseline"):
        client.post(f"/experiments/{experiment_id}/{step}")
    body = client.post(f"/experiments/{experiment_id}/inject").json()
    assert body["state"] == "OBSERVING"
    return experiment_id, body


@pytest.mark.parametrize("mode", ["GRACEFUL", "FORCE"])
def test_mode_reaches_provider_and_evidence(
    client: TestClient, chaos: FakeChaos, mode: str
) -> None:
    _, body = run_to_observing(client, mode)

    (request,) = chaos.requests
    assert request.mode == mode
    assert body["chaos"]["pod_delete_mode"] == mode


@pytest.mark.parametrize("mode", ["GRACEFUL", "FORCE"])
def test_score_records_mode_without_mode_penalty(
    client: TestClient,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
    mode: str,
) -> None:
    """Same evidence -> same number, whatever the mode; the mode is context only."""
    experiment_id, body = run_to_observing(client, mode)
    start = datetime.fromisoformat(body["chaos"]["created_at"])
    chaos.statuses, chaos.status_calls = [COMPLETED_PASS], 0
    prometheus.healthy_recovery(start.timestamp())
    clock.now = start + timedelta(seconds=120)

    observe(client, experiment_id)
    score = client.get(f"/experiments/{experiment_id}/score").json()

    assert score["score"] == 100.0
    assert score["inputs"]["fault"]["pod_delete_mode"] == mode
    assert f"for pod-delete ({mode})" in score["explanation"]
    v1 = client.get(f"/experiments/{experiment_id}/score?version=v1").json()
    assert v1["inputs"]["fault"]["pod_delete_mode"] == mode


def test_force_and_graceful_with_identical_evidence_score_identically(
    client: TestClient, chaos: FakeChaos, prometheus: FakePrometheus, clock: Clock
) -> None:
    scores = {}
    for mode in ("GRACEFUL", "FORCE"):
        chaos.requests.clear()
        experiment_id, body = run_to_observing(client, mode)
        start = datetime.fromisoformat(body["chaos"]["created_at"])
        chaos.statuses, chaos.status_calls = [COMPLETED_PASS], 0
        prometheus.healthy_recovery(start.timestamp())
        prometheus.client_counters(start.timestamp(), {2: {"connection_error": 6}})
        clock.now = start + timedelta(seconds=120)
        observe(client, experiment_id)
        scores[mode] = client.get(f"/experiments/{experiment_id}/score").json()

    assert scores["GRACEFUL"]["score"] == scores["FORCE"]["score"] < 100
    numbers = lambda s: [
        (c["name"], c["normalized"], c["effective_weight"], c["contribution"])
        for c in s["components"]
    ]
    assert numbers(scores["GRACEFUL"]) == numbers(scores["FORCE"])
