"""The topology builder: only verifiable relationships, explicit unknowns, allowlist."""

import json
import random
from typing import Any

from app.domain.safety_policy import SYSTEM_NAMESPACES
from app.integrations.kubernetes_adapter import ListingError
from app.schemas.topology import Topology
from app.services.topology.graph import SCHEMA, build_topology, node_id
from tests import topology_fixtures as fx

EXECUTION = {
    "context": "kind-autoresilience",
    "role": "execution",
    "chaos_permitted": True,
    "namespaces": None,
}
DISCOVERY = {
    "context": "kind-staging",
    "role": "discovery",
    "chaos_permitted": False,
    "namespaces": ["shop"],
}


def build(
    snapshot: Any = None,
    namespaces: list[str] | None = None,
    cluster: dict[str, Any] = EXECUTION,
) -> dict[str, Any]:
    result = build_topology(
        snapshot or fx.snapshot(),
        namespaces=namespaces,
        excluded=SYSTEM_NAMESPACES,
        cluster=cluster,
    )
    Topology.model_validate(result)  # every result satisfies the contract
    return result


def edges(t: dict[str, Any], type_: str) -> set[tuple[str, str]]:
    return {(e["source"], e["target"]) for e in t["edges"] if e["type"] == type_}


def nodes(t: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in t["nodes"]}


def unknowns(t: dict[str, Any], type_: str) -> list[dict[str, Any]]:
    return [u for u in t["unknowns"] if u["type"] == type_]


D = node_id("Deployment", "shop", "checkout")
RS = node_id("ReplicaSet", "shop", "checkout-7d9")
OLD_RS = node_id("ReplicaSet", "shop", "checkout-5c4")
PA = node_id("Pod", "shop", "checkout-7d9-a")
PB = node_id("Pod", "shop", "checkout-7d9-b")
SVC = node_id("Service", "shop", "checkout")
SLICE = node_id("EndpointSlice", "shop", "checkout-abc")
NODE = node_id("Node", None, fx.NODE)


def test_contract_header_and_stable_ids() -> None:
    t = build()
    assert t["schema"] == SCHEMA == "autoresilience-topology/1"
    assert t["observed_at"] == fx.OBSERVED_AT
    assert t["traffic"]["observed"] is False
    assert D == "Deployment:shop/checkout" and NODE == f"Node:{fx.NODE}"
    assert nodes(t)[D]["uid"] == "d-checkout"


def test_ownership_edges_are_uid_verified_controller_references() -> None:
    t = build()
    assert edges(t, "owns") == {
        (D, RS),
        (D, OLD_RS),
        (RS, PA),
        (RS, PB),
        (
            node_id("StatefulSet", "shop", "cart-redis"),
            node_id("Pod", "shop", "cart-redis-0"),
        ),
        (SVC, SLICE),
    }
    owns = next(e for e in t["edges"] if e["id"] == f"owns:{D}->{RS}")
    assert owns["provenance"]["source"] == "metadata.ownerReferences"


def test_owner_with_a_different_uid_is_an_unknown_not_an_edge() -> None:
    objects = fx.shop()
    objects["replicasets"][0]["metadata"]["ownerReferences"][0]["uid"] = "recreated"
    t = build(fx.snapshot(objects))
    assert (D, RS) not in edges(t, "owns")
    [mismatch] = unknowns(t, "owner_uid_mismatch")
    assert mismatch["subject"] == RS


def test_non_controller_references_are_ignored() -> None:
    objects = fx.shop()
    objects["pods"][0]["metadata"]["ownerReferences"][0]["controller"] = False
    assert (RS, PA) not in edges(build(fx.snapshot(objects)), "owns")


def test_owner_of_an_unlisted_kind_is_reported() -> None:
    t = build()
    job = [u for u in unknowns(t, "owner_not_observed") if "Job" in u["detail"]]
    assert job[0]["subject"] == node_id("Pod", "shop", "migrate-x1")
    assert "not part of the topology" in job[0]["detail"]


def test_selector_edges_match_labels_in_the_same_namespace_only() -> None:
    t = build()
    assert edges(t, "selects") == {(SVC, PA), (SVC, PB)}
    # A Pod with matching labels in another namespace is never linked.
    assert node_id("Pod", "staging", "checkout-copy") in nodes(t)
    assert all(
        target != node_id("Pod", "staging", "checkout-copy")
        for _, target in edges(t, "selects")
    )


def test_endpoint_edges_carry_conditions_and_missing_targets_are_unknowns() -> None:
    t = build()
    assert edges(t, "endpoint") == {(SLICE, PA), (SLICE, PB)}
    by_id = {e["id"]: e for e in t["edges"]}
    assert by_id[f"endpoint:{SLICE}->{PB}"]["attributes"]["ready"] is False
    assert by_id[f"endpoint:{SLICE}->{PA}"]["attributes"]["ready"] is True
    [gone] = unknowns(t, "endpoint_target_not_observed")
    assert "checkout-old" in gone["detail"] and gone["subject"] == SLICE


def test_slice_without_owner_reference_links_by_service_name_label() -> None:
    objects = fx.shop()
    del objects["endpointslices"][0]["metadata"]["ownerReferences"]
    t = build(fx.snapshot(objects))
    assert edges(t, "slice_for") == {(SLICE, SVC)}
    assert (SVC, SLICE) not in edges(t, "owns")
    assert nodes(t)[SVC]["health"] == "DEGRADED"  # still computed from the slice


def test_scheduling_edges_and_missing_nodes() -> None:
    t = build()
    assert (PA, NODE) in edges(t, "scheduled_on")
    [lost] = unknowns(t, "node_not_observed")
    assert lost["subject"] == node_id("Pod", "shop", "orphan")
    assert "worker-gone" in lost["detail"]
    assert node_id("Node", None, "worker-gone") not in nodes(t)


def test_nodes_that_cannot_be_listed_are_unknown_for_every_pod() -> None:
    objects = fx.shop()
    objects["nodes"] = []
    errors = [ListingError("nodes", None, 403, "Forbidden")]
    t = build(fx.snapshot(objects, errors))
    assert not edges(t, "scheduled_on")
    lost = unknowns(t, "node_not_observed")
    assert all("could not be listed" in u["detail"] for u in lost) and len(lost) == 6
    [forbidden] = unknowns(t, "listing_forbidden")
    assert forbidden["resource"] == "nodes"


def test_system_namespaces_are_excluded_and_scope_filters() -> None:
    t = build()
    assert not [n for n in t["nodes"] if n["namespace"] in SYSTEM_NAMESPACES]
    assert t["scope"]["excluded_namespaces"] == sorted(SYSTEM_NAMESPACES)

    scoped = build(namespaces=["shop"])
    assert {n["namespace"] for n in scoped["nodes"]} == {"shop", None}
    assert scoped["scope"]["namespaces"] == ["shop"]


def test_selectorless_and_external_name_services_are_unknowns() -> None:
    t = build()
    subjects = {u["subject"] for u in unknowns(t, "service_without_selector")}
    assert subjects == {
        node_id("Service", "shop", "legacy-db"),
        node_id("Service", "shop", "payments"),
    }
    assert nodes(t)[node_id("Service", "shop", "payments")]["health"] == "UNKNOWN"


def test_health_comes_from_reported_status() -> None:
    n = nodes(build())
    assert (n[D]["health"], n[D]["health_reason"]) == (
        "DEGRADED",
        "1/2 ready (controller status)",
    )
    assert n[OLD_RS]["health"] == "SCALED_TO_ZERO"
    assert n[OLD_RS]["replicas"]["revision"] == "1"
    assert (n[PA]["health"], n[PB]["health"]) == ("HEALTHY", "DEGRADED")
    assert n[PB]["pod"]["restarts"] == 4
    assert n[PB]["pod"]["containers"][0]["reason"] == "CrashLoopBackOff"
    assert n[node_id("Pod", "shop", "migrate-x1")]["health"] == "COMPLETED"
    assert (n[SVC]["health"], n[SVC]["health_reason"]) == (
        "DEGRADED",
        "2/3 endpoints ready",
    )
    assert n[NODE]["health"] == "HEALTHY" and n[NODE]["node"]["roles"] == [
        "control-plane"
    ]


def test_service_health_unknown_when_slices_cannot_be_listed() -> None:
    objects = fx.shop()
    objects["endpointslices"] = []
    errors = [ListingError("endpointslices", "shop", 403, "Forbidden")]
    t = build(fx.snapshot(objects, errors), namespaces=["shop"])
    assert nodes(t)[SVC]["health"] == "UNKNOWN"
    assert unknowns(t, "listing_forbidden")[0]["namespace"] == "shop"


def test_failed_and_truncated_listings_are_reported() -> None:
    errors = [ListingError("events", None, 500, "Internal Server Error")]
    t = build(fx.snapshot(errors=errors, truncated=[("pods", "shop")]))
    assert "500" in unknowns(t, "listing_failed")[0]["detail"]
    assert unknowns(t, "listing_truncated")[0]["resource"] == "pods"


def test_out_of_scope_listing_errors_are_not_reported() -> None:
    errors = [ListingError("pods", "other", 403, "Forbidden")]
    assert not unknowns(
        build(fx.snapshot(errors=errors), namespaces=["shop"]), "listing_forbidden"
    )


def test_malformed_objects_are_skipped_and_reported() -> None:
    objects = fx.shop()
    objects["pods"].append({"metadata": {"namespace": "shop"}})
    objects["pods"].append({"metadata": "garbage", "status": None})
    objects["services"][0]["spec"]["ports"] = None
    t = build(fx.snapshot(objects))
    assert len(unknowns(t, "malformed_object")) == 2
    assert nodes(t)[SVC]["service"]["ports"] == []


def test_events_attach_to_the_same_object_newest_first() -> None:
    events = nodes(build())[PB]["events"]
    assert [e["reason"] for e in events] == ["BackOff", "Unhealthy"]


def test_only_allowlisted_fields_leave_the_builder() -> None:
    text = json.dumps(build(), default=str)
    assert fx.SECRET_VALUE not in text
    assert "DB_PASSWORD" not in text
    assert "last-applied-configuration" not in text


def test_output_is_deterministic_regardless_of_listing_order() -> None:
    first = build()
    shuffled = fx.shop()
    for items in shuffled.values():
        random.Random(7).shuffle(items)
    assert build(fx.snapshot(shuffled)) == first


def test_experiment_targets_only_on_the_execution_cluster() -> None:
    n = nodes(build())
    assert n[D]["experiment_target"]["supported"] is True
    assert n[PA]["experiment_target"] is None and n[RS]["experiment_target"] is None
    readonly = nodes(build(namespaces=["shop"], cluster=DISCOVERY))[D]
    assert readonly["experiment_target"]["supported"] is False
    assert "Read-only" in readonly["experiment_target"]["reason"]


def test_empty_snapshot_is_a_valid_empty_graph() -> None:
    t = build(fx.snapshot({}))
    assert (t["nodes"], t["edges"], t["unknowns"], t["counts"]) == ([], [], [], {})
