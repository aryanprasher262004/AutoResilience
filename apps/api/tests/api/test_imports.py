"""P7 import workflow over HTTP: preview -> save -> approve -> deploy -> health ->
topology -> experiment eligibility -> ownership-checked removal."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import AppImport, Application
from app.schemas.imports import DeploymentPlan
from tests.conftest import Clock, FakeKubernetes, FakeProvisioner
from tests.import_fixtures import COMPOSE, ENV_SECRET, deployed, request

TRAFFIC = [{"service": "api", "port": 9898, "path": "/version"}]


def save(client: TestClient, **extra: Any) -> dict[str, Any]:
    response = client.post("/imports", json=request(traffic=TRAFFIC, **extra))
    assert response.status_code == 201, response.text
    return response.json()


def approve(client: TestClient, imp: dict[str, Any]) -> Any:
    return client.post(
        f"/imports/{imp['id']}/deploy",
        json={"plan_digest": imp["plan"]["digest"], "confirm": True},
    )


def healthy(kubernetes: FakeKubernetes, imp: dict[str, Any], **kwargs: Any) -> None:
    kubernetes.snapshot_result = deployed(
        DeploymentPlan.model_validate(imp["plan"]), **kwargs
    )


def ready_import(client: TestClient, kubernetes: FakeKubernetes) -> dict[str, Any]:
    imp = save(client)
    assert approve(client, imp).json()["status"] == "DEPLOYING"
    healthy(kubernetes, imp)
    body = client.post(f"/imports/{imp['id']}/refresh").json()
    assert body["status"] == "READY", body["deployment"]
    return body


def test_preview_is_stateless_and_never_deploys(
    client: TestClient, db_session: Session, provisioner: FakeProvisioner
) -> None:
    body = client.post("/imports/preview", json=request()).json()
    assert body["deployable"] and body["plan"]["namespace"] == "ar-imp-shop"
    assert ENV_SECRET not in str(body)
    assert db_session.query(AppImport).count() == 0
    assert provisioner.applied == []


def test_saving_stores_the_plan_but_deploys_nothing(
    client: TestClient, provisioner: FakeProvisioner
) -> None:
    imp = save(client)
    assert imp["status"] == "PLANNED"
    assert ENV_SECRET not in str(imp)
    assert provisioner.applied == []
    assert client.post("/imports", json=request()).status_code == 409


def test_blocking_findings_cannot_be_saved(client: TestClient) -> None:
    bad = COMPOSE.replace("deploy: {replicas: 2}", "privileged: true")
    response = client.post("/imports", json=request(bad))
    assert response.status_code == 422
    preview = client.post("/imports/preview", json=request(bad)).json()
    assert not preview["deployable"] and preview["plan"] is None


def test_deploy_requires_the_reviewed_digest_and_explicit_confirmation(
    client: TestClient, provisioner: FakeProvisioner
) -> None:
    imp = save(client)
    url = f"/imports/{imp['id']}/deploy"
    assert (
        client.post(url, json={"plan_digest": imp["plan"]["digest"]}).status_code == 422
    )
    assert (
        client.post(
            url, json={"plan_digest": imp["plan"]["digest"], "confirm": False}
        ).status_code
        == 422
    )
    stale = client.post(url, json={"plan_digest": "0" * 64, "confirm": True})
    assert stale.status_code == 409 and "review it again" in stale.json()["detail"]
    assert provisioner.applied == []
    body = approve(client, imp).json()
    assert body["status"] == "DEPLOYING" and body["deployment"]["attempts"] == 1
    namespace, import_id, _objects = provisioner.applied[0]
    assert (namespace, import_id) == ("ar-imp-shop", imp["id"])
    assert approve(client, imp).status_code == 409  # not twice


def test_deploy_needs_the_dedicated_identity_on_the_execution_cluster(
    client: TestClient, provisioner: FakeProvisioner
) -> None:
    imp = save(client)
    provisioner.configured = False
    assert approve(client, imp).status_code == 503
    provisioner.configured, provisioner.identity_ok = True, False
    assert "kubernetes-admin" in approve(client, imp).json()["detail"]
    provisioner.identity_ok, provisioner.fingerprint = True, "another-cluster"
    assert "different cluster" in approve(client, imp).json()["detail"]
    assert provisioner.applied == []
    assert client.get(f"/imports/{imp['id']}").json()["status"] == "PLANNED"


def test_an_existing_namespace_that_is_not_ours_fails_safely(
    client: TestClient, provisioner: FakeProvisioner
) -> None:
    provisioner.foreign.add("ar-imp-shop")
    imp = save(client)
    body = approve(client, imp).json()
    assert body["status"] == "FAILED"
    assert "not created by this import" in body["deployment"]["error"]
    assert provisioner.applied == []


def test_healthy_deployment_becomes_ready_and_onboarded(
    client: TestClient, kubernetes: FakeKubernetes, db_session: Session
) -> None:
    body = ready_import(client, kubernetes)
    assert {w["name"]: w["state"] for w in body["deployment"]["workloads"]} == {
        "web": "READY",
        "api": "READY",
        "autoresilience-loadgen": "READY",
    }
    app = db_session.get(Application, uuid.UUID(body["application_id"]))
    assert app is not None and app.namespaces == ["ar-imp-shop"]
    assert kubernetes.snapshot_calls[-1] == ["ar-imp-shop"]


def test_failures_are_reported_after_a_grace_period_and_can_be_retried(
    client: TestClient,
    kubernetes: FakeKubernetes,
    clock: Clock,
    provisioner: FakeProvisioner,
) -> None:
    clock.now = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    imp = save(client)
    approve(client, imp)
    healthy(kubernetes, imp, reason="ImagePullBackOff")
    first = client.post(f"/imports/{imp['id']}/refresh").json()
    assert first["status"] == "DEPLOYING"  # a blip is not a verdict
    clock.now += timedelta(seconds=60)
    failed = client.post(f"/imports/{imp['id']}/refresh").json()
    assert failed["status"] == "FAILED"
    assert failed["deployment"]["error"].startswith("Image pull failed")
    assert "image name and tag" in failed["deployment"]["recovery"]
    # Retry: the user approves again; nothing retries by itself.
    assert approve(client, imp).json()["deployment"]["attempts"] == 2
    assert len(provisioner.applied) == 2


def test_topology_marks_imported_resources_and_declared_relations(
    client: TestClient, kubernetes: FakeKubernetes
) -> None:
    body = ready_import(client, kubernetes)
    topo = client.get(f"/applications/{body['application_id']}/topology").json()
    assert topo["schema"] == "autoresilience-topology/1"
    nodes = {n["id"]: n for n in topo["nodes"]}
    web = nodes["Deployment:ar-imp-shop/web"]
    assert web["origin"] == {
        "import_id": body["id"],
        "import_name": "shop",
        "role": "application",
        "workload": "web",
    }
    assert web["experiment_target"]["supported"] is True
    loadgen = nodes["Deployment:ar-imp-shop/autoresilience-loadgen"]
    assert loadgen["origin"]["role"] == "load-generator"
    assert loadgen["experiment_target"]["supported"] is False
    overlay = topo["imported"]
    assert overlay["declared"] == [
        {
            "type": "depends_on",
            "source": "Deployment:ar-imp-shop/web",
            "target": "Deployment:ar-imp-shop/api",
            "detail": overlay["declared"][0]["detail"],
            "verified": False,
        }
    ]
    # Declared relations never become edges, and traffic stays unobserved.
    assert not [
        e
        for e in topo["edges"]
        if e["type"] not in ("owns", "selects", "endpoint", "slice_for", "scheduled_on")
    ]
    assert topo["traffic"]["observed"] is False
    assert {p["id"]: p["observed"] for p in overlay["planned"]}[
        "Service:ar-imp-shop/web"
    ] is True


def test_imported_workloads_become_targets_only_once_ready(
    client: TestClient, kubernetes: FakeKubernetes
) -> None:
    def create(name: str) -> Any:
        return client.post(
            "/experiments",
            json={
                "name": "imported",
                "target": {
                    "namespace": "ar-imp-shop",
                    "kind": "Deployment",
                    "name": name,
                },
                "fault_type": "pod-delete",
                "duration_seconds": 30,
                "affected_replicas": 1,
            },
        )

    unknown = create("web")
    assert unknown.status_code == 422 and "has no import" in str(unknown.json())
    imp = save(client)
    approve(client, imp)
    assert "DEPLOYING" in str(create("web").json())
    healthy(kubernetes, imp)
    client.post(f"/imports/{imp['id']}/refresh")
    assert create("web").status_code == 201
    assert "load generator" in str(create("autoresilience-loadgen").json())
    assert "not a workload" in str(create("other").json())


def test_removal_needs_the_typed_name_and_ends_with_the_namespace_gone(
    client: TestClient,
    kubernetes: FakeKubernetes,
    provisioner: FakeProvisioner,
    db_session: Session,
) -> None:
    body = ready_import(client, kubernetes)
    url = f"/imports/{body['id']}/remove"
    assert client.post(url, json={"confirm_name": "wrong"}).status_code == 409
    assert provisioner.removed == []
    removing = client.post(url, json={"confirm_name": "shop"}).json()
    assert removing["status"] == "REMOVING" and removing["application_id"] is None
    assert provisioner.removed == [("ar-imp-shop", body["id"])]
    assert db_session.get(Application, uuid.UUID(body["application_id"])) is None
    provisioner.phase = "absent"
    assert client.post(f"/imports/{body['id']}/refresh").json()["status"] == "REMOVED"
    assert client.delete(f"/imports/{body['id']}").status_code == 204
    # The name can be imported again.
    assert client.post("/imports", json=request()).status_code == 201


def test_removal_refuses_a_namespace_it_cannot_prove_it_owns(
    client: TestClient, kubernetes: FakeKubernetes, provisioner: FakeProvisioner
) -> None:
    body = ready_import(client, kubernetes)
    provisioner.foreign.add("ar-imp-shop")
    response = client.post(
        f"/imports/{body['id']}/remove", json={"confirm_name": "shop"}
    )
    assert response.status_code == 409 and "not labelled" in response.json()["detail"]
    assert client.get(f"/imports/{body['id']}").json()["status"] == "READY"
    assert client.delete(f"/imports/{body['id']}").status_code == 409


def test_a_never_deployed_import_is_removed_without_touching_the_cluster(
    client: TestClient, provisioner: FakeProvisioner
) -> None:
    imp = save(client)
    body = client.post(
        f"/imports/{imp['id']}/remove", json={"confirm_name": "shop"}
    ).json()
    assert body["status"] == "REMOVED" and provisioner.removed == []


def test_the_imported_application_cannot_be_deleted_behind_the_import(
    client: TestClient, kubernetes: FakeKubernetes
) -> None:
    body = ready_import(client, kubernetes)
    response = client.delete(f"/applications/{body['application_id']}")
    assert response.status_code == 409


def test_capabilities_report_whether_deployment_is_possible(
    client: TestClient, provisioner: FakeProvisioner
) -> None:
    caps = client.get("/imports/capabilities").json()
    assert caps["provisioner"]["configured"] is True
    assert caps["namespace_prefix"] == "ar-imp-"
    provisioner.configured = False
    caps = client.get("/imports/capabilities").json()
    assert caps["provisioner"]["configured"] is False
    assert "reviewed and saved, not deployed" in caps["provisioner"]["detail"]
