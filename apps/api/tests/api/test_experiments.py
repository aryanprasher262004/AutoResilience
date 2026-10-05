import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Experiment


def payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "checkout pod-kill",
        "description": "first run",
        "target": {"namespace": "shop", "kind": "Deployment", "name": "checkout"},
        "fault_type": "pod-delete",
        "duration_seconds": 60,
        "affected_replicas": 1,
    }
    body.update(overrides)
    return body


def test_health_still_ok(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_create_experiment_persists_with_created_state(
    client: TestClient, db_session: Session
) -> None:
    response = client.post("/experiments", json=payload())

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "checkout pod-kill"
    assert body["state"] == "CREATED"
    assert body["target"] == {
        "namespace": "shop",
        "kind": "Deployment",
        "name": "checkout",
    }
    assert body["fault_type"] == "pod-delete"
    assert body["validation_result"] is None

    stored = db_session.get(Experiment, uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.state == "CREATED"
    assert stored.target_name == "checkout"


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"target": {"namespace": "Shop_NS", "kind": "Deployment", "name": "checkout"}},
        {"target": {"namespace": "shop", "kind": "DaemonSet", "name": "checkout"}},
        {"target": {"namespace": "shop", "kind": "Deployment", "name": "-bad-"}},
        {"target": {"namespace": "a" * 64, "kind": "Deployment", "name": "x"}},
        {"fault_type": "node-drain"},
        {"duration_seconds": 0},
        {"affected_replicas": 0},
    ],
)
def test_create_experiment_rejects_malformed_input(
    client: TestClient, db_session: Session, overrides: dict[str, Any]
) -> None:
    assert client.post("/experiments", json=payload(**overrides)).status_code == 422
    assert db_session.query(Experiment).count() == 0


def test_create_experiment_requires_target(client: TestClient) -> None:
    body = payload()
    del body["target"]
    assert client.post("/experiments", json=body).status_code == 422


def test_list_experiments_returns_created(client: TestClient) -> None:
    assert client.get("/experiments").json() == []

    first = client.post("/experiments", json=payload(name="a")).json()
    second = client.post("/experiments", json=payload(name="b")).json()

    ids = {e["id"] for e in client.get("/experiments").json()}
    assert ids == {first["id"], second["id"]}


def test_get_experiment_by_id(client: TestClient) -> None:
    created = client.post("/experiments", json=payload()).json()

    response = client.get(f"/experiments/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_experiment_returns_404(client: TestClient) -> None:
    response = client.get(f"/experiments/{uuid.uuid4()}")
    assert response.status_code == 404


def test_get_experiment_with_invalid_id_returns_422(client: TestClient) -> None:
    assert client.get("/experiments/not-a-uuid").status_code == 422
