"""Clusters, namespaces, topology and applications: scoping, permissions, errors."""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.domain.experiment import WorkloadKind
from app.integrations.kubernetes_adapter import ListingError, WorkloadSummary
from tests import topology_fixtures as fx
from tests.conftest import EXECUTION_CONTEXT, Clusters, FakeKubernetes

CREATED = datetime(2026, 10, 1, tzinfo=UTC)


def workload(namespace: str, name: str) -> WorkloadSummary:
    return WorkloadSummary(
        namespace, WorkloadKind.DEPLOYMENT, name, 2, 2, 2, 2, CREATED
    )


@pytest.fixture
def cluster(kubernetes: FakeKubernetes) -> FakeKubernetes:
    kubernetes.workloads = [
        workload("shop", "checkout"),
        workload("shop", "frontend"),
        workload("resilience-sandbox", "fragile"),
        workload("kube-system", "coredns"),
    ]
    kubernetes.namespaces = [
        "default",
        "kube-system",
        "monitoring",
        "resilience-sandbox",
        "shop",
    ]
    kubernetes.snapshot_result = fx.snapshot()
    return kubernetes


@pytest.fixture
def staging(clusters: Clusters) -> FakeKubernetes:
    fake = clusters.discover("kind-staging", ["shop", "payments"])
    fake.workloads = [workload("shop", "checkout")]
    fake.namespace_errors = {"payments": 403}
    fake.snapshot_result = fx.snapshot()
    return fake


# --- clusters and namespaces ------------------------------------------------------------


def test_clusters_lists_execution_and_authorized_discovery_contexts(
    client: TestClient, staging: FakeKubernetes
) -> None:
    items = client.get("/clusters").json()["items"]
    assert items == [
        {
            "context": EXECUTION_CONTEXT,
            "role": "execution",
            "chaos_permitted": True,
            "namespaces": None,
        },
        {
            "context": "kind-staging",
            "role": "discovery",
            "chaos_permitted": False,
            "namespaces": ["shop", "payments"],
        },
    ]
    assert staging.snapshot_calls == []  # listing contexts contacts no cluster


def test_execution_namespaces_hide_system_namespaces_and_count_workloads(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    body = client.get("/clusters/namespaces").json()
    assert body["source"] == "namespaces"
    assert [(n["name"], n["workloads"]) for n in body["items"]] == [
        ("default", 0),
        ("resilience-sandbox", 1),
        ("shop", 2),
    ]
    assert "kube-system" in body["excluded_namespaces"]


def test_namespaces_fall_back_to_workloads_without_namespace_access(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    cluster.namespaces = None  # 403: an engine granted before P6
    body = client.get("/clusters/namespaces").json()
    assert body["source"] == "workloads"
    assert [n["name"] for n in body["items"]] == ["resilience-sandbox", "shop"]


def test_discovery_namespaces_are_the_granted_ones_with_access_status(
    client: TestClient, staging: FakeKubernetes
) -> None:
    body = client.get("/clusters/namespaces", params={"context": "kind-staging"}).json()
    assert body["source"] == "configured"
    assert [(n["name"], n["access"], n["workloads"]) for n in body["items"]] == [
        ("shop", "readable", 1),
        ("payments", "forbidden", None),
    ]


def test_unknown_context_is_404_and_never_read(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    for path in ("/clusters/namespaces", "/topology"):
        response = client.get(path, params={"context": "prod"})
        assert response.status_code == 404
        assert "not authorized" in response.json()["detail"]
    assert cluster.snapshot_calls == []


def test_unreachable_cluster_is_503(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    cluster.error = "Kubernetes API unreachable: connection refused"
    for path in ("/clusters/namespaces", "/topology"):
        response = client.get(path)
        assert response.status_code == 503
        assert "unreachable" in response.json()["detail"]


# --- topology ----------------------------------------------------------------------------


def test_topology_of_the_execution_cluster(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    body = client.get("/topology").json()
    assert body["schema"] == "autoresilience-topology/1"
    assert body["cluster"]["role"] == "execution"
    assert cluster.snapshot_calls == [None]  # all namespaces, filtered server-side
    assert {n["namespace"] for n in body["nodes"]} == {"shop", "staging", None}

    client.get("/topology", params={"namespace": ["shop", "shop"]})
    assert cluster.snapshot_calls[-1] == ["shop"]


def test_topology_refuses_system_and_ungranted_namespaces(
    client: TestClient, cluster: FakeKubernetes, staging: FakeKubernetes
) -> None:
    response = client.get("/topology", params={"namespace": "kube-system"})
    assert response.status_code == 422
    response = client.get(
        "/topology", params={"context": "kind-staging", "namespace": "default"}
    )
    assert response.status_code == 422
    assert "not among the namespaces granted" in response.json()["detail"]
    assert cluster.snapshot_calls == staging.snapshot_calls == []


def test_discovery_topology_reads_only_granted_namespaces_and_offers_no_chaos(
    client: TestClient, staging: FakeKubernetes
) -> None:
    body = client.get("/topology", params={"context": "kind-staging"}).json()
    assert staging.snapshot_calls == [["shop", "payments"]]
    assert body["cluster"]["chaos_permitted"] is False
    targets = [n["experiment_target"] for n in body["nodes"] if n["experiment_target"]]
    assert targets and not any(t["supported"] for t in targets)


def test_forbidden_listings_surface_as_unknowns(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    cluster.snapshot_result = fx.snapshot(
        errors=[ListingError("endpointslices", None, 403, "Forbidden")]
    )
    body = client.get("/topology").json()
    assert {"listing_forbidden"} <= {u["type"] for u in body["unknowns"]}


# --- applications -----------------------------------------------------------------------


def create(client: TestClient, **overrides: object) -> httpx.Response:
    payload = {"name": "Shop", "namespaces": ["shop"], **overrides}
    return client.post("/applications", json=payload)


def test_application_lifecycle(client: TestClient, cluster: FakeKubernetes) -> None:
    response = create(
        client, name="  Shop  ", namespaces=["shop", "resilience-sandbox"]
    )
    assert response.status_code == 201
    app = response.json()
    assert app["name"] == "Shop"
    assert app["context"] == EXECUTION_CONTEXT
    assert app["namespaces"] == ["resilience-sandbox", "shop"]
    assert app["cluster"]["role"] == "execution"

    assert [a["id"] for a in client.get("/applications").json()["items"]] == [app["id"]]
    assert client.get(f"/applications/{app['id']}").json() == app

    topology = client.get(f"/applications/{app['id']}/topology").json()
    assert topology["application_id"] == app["id"]
    assert cluster.snapshot_calls[-1] == ["resilience-sandbox", "shop"]

    calls = len(cluster.snapshot_calls)
    assert client.delete(f"/applications/{app['id']}").status_code == 204
    assert len(cluster.snapshot_calls) == calls  # forgetting never touches the cluster
    assert client.get(f"/applications/{app['id']}").status_code == 404


def test_application_names_are_unique(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    assert create(client).status_code == 201
    response = create(client)
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"context": "prod"}, "context", "not authorized"),
        ({"namespaces": ["kube-system"]}, "namespaces", "system namespace"),
        ({"namespaces": ["missing"]}, "namespaces", "Not found or not readable"),
        ({"namespaces": ["Not_A_Name"]}, "namespaces", "not a namespace name"),
        ({"namespaces": []}, "namespaces", "at least 1"),
        ({"name": "   "}, "name", "blank"),
    ],
)
def test_application_validation_maps_onto_fields(
    client: TestClient,
    cluster: FakeKubernetes,
    overrides: dict[str, object],
    field: str,
    message: str,
) -> None:
    response = create(client, **overrides)
    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"][:2] == ["body", field]
    assert message in error["msg"]


def test_discovery_application_requires_readable_namespaces(
    client: TestClient, staging: FakeKubernetes
) -> None:
    response = create(client, context="kind-staging", namespaces=["payments"])
    assert response.status_code == 422
    response = create(client, context="kind-staging", namespaces=["shop"])
    assert response.status_code == 201
    assert response.json()["cluster"]["chaos_permitted"] is False


def test_application_on_unreachable_cluster_is_503(
    client: TestClient, cluster: FakeKubernetes
) -> None:
    cluster.error = "Kubernetes API unreachable"
    assert create(client).status_code == 503


def test_application_whose_context_is_no_longer_authorized(
    client: TestClient, clusters: Clusters, staging: FakeKubernetes
) -> None:
    app = create(client, context="kind-staging", namespaces=["shop"]).json()
    del clusters.discovery["kind-staging"]  # operator removed the import

    read = client.get(f"/applications/{app['id']}").json()
    assert read["cluster"] is None and read["context"] == "kind-staging"
    response = client.get(f"/applications/{app['id']}/topology")
    assert response.status_code == 409
    assert "no longer authorized" in response.json()["detail"]
    assert staging.snapshot_calls == []


def test_application_with_a_revoked_namespace(
    client: TestClient, clusters: Clusters, staging: FakeKubernetes
) -> None:
    app = create(client, context="kind-staging", namespaces=["shop"]).json()
    clusters.discovery["kind-staging"] = (["payments"], staging)
    assert client.get(f"/applications/{app['id']}").json()["cluster"] is None
    assert client.get(f"/applications/{app['id']}/topology").status_code == 409
