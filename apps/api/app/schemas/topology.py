"""Topology contract `autoresilience-topology/1` (docs/topology.md).

Additive changes only within /1; anything that changes the meaning of a field is /2.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

NodeKind = Literal[
    "Deployment", "ReplicaSet", "StatefulSet", "Pod", "Service", "EndpointSlice", "Node"
]
# HEALTHY / DEGRADED / UNAVAILABLE / SCALED_TO_ZERO as for Services; COMPLETED: a
# Succeeded Pod; UNKNOWN: not determinable from what could be read.
NodeHealth = Literal[
    "HEALTHY", "DEGRADED", "UNAVAILABLE", "SCALED_TO_ZERO", "COMPLETED", "UNKNOWN"
]
EdgeType = Literal["owns", "selects", "endpoint", "slice_for", "scheduled_on"]
UnknownType = Literal[
    "listing_forbidden",
    "listing_failed",
    "listing_truncated",
    "owner_not_observed",
    "owner_uid_mismatch",
    "node_not_observed",
    "service_without_selector",
    "endpoint_target_not_observed",
    "malformed_object",
]
ClusterRole = Literal["execution", "discovery"]


class ClusterRef(BaseModel):
    # None only when the engine uses the kubeconfig's current context (development).
    context: str | None
    # execution: KUBE_CONTEXT, where experiments run; discovery: read-only.
    role: ClusterRole
    chaos_permitted: bool
    # None: every namespace outside the excluded system namespaces.
    namespaces: list[str] | None


class Replicas(BaseModel):
    """Controller status (spec.replicas and status.*), as `kubectl get` shows it."""

    desired: int
    current: int
    ready: int
    available: int
    updated: int
    selector: str | None
    # ReplicaSets only: the Deployment revision annotation.
    revision: str | None = None


class Container(BaseModel):
    name: str
    image: str
    ready: bool
    restart_count: int
    # waiting | running | terminated, with its reason (e.g. CrashLoopBackOff).
    state: str | None
    reason: str | None


class PodDetails(BaseModel):
    phase: str
    ready: bool
    terminating: bool
    restarts: int
    node_name: str | None
    pod_ip: str | None
    start_time: datetime | None
    containers: list[Container]


class ServicePort(BaseModel):
    name: str | None
    port: int
    target_port: str | None
    protocol: str


class ServiceDetails(BaseModel):
    type: str
    cluster_ip: str | None
    selector: dict[str, str] | None
    ports: list[ServicePort]


class SlicePort(BaseModel):
    name: str | None
    port: int
    protocol: str


class EndpointSliceDetails(BaseModel):
    address_type: str | None
    endpoints: int
    ready: int
    ports: list[SlicePort]


class NodeDetails(BaseModel):
    ready: str | None  # the Ready condition: "True" | "False" | "Unknown"
    roles: list[str]
    unschedulable: bool
    kubelet_version: str | None
    os_image: str | None
    architecture: str | None


class TargetSupport(BaseModel):
    """Whether the experiment builder may be offered; validation stays authoritative."""

    supported: bool
    reason: str


class TopologyEvent(BaseModel):
    type: str
    reason: str
    message: str
    count: int
    last_seen: datetime | None


class TopologyNode(BaseModel):
    # "<Kind>:<namespace>/<name>", or "Node:<name>"; stable across snapshots.
    id: str
    kind: NodeKind
    namespace: str | None
    name: str
    uid: str | None
    labels: dict[str, str]
    created_at: datetime | None
    health: NodeHealth
    health_reason: str
    replicas: Replicas | None
    pod: PodDetails | None
    service: ServiceDetails | None
    endpoint_slice: EndpointSliceDetails | None
    node: NodeDetails | None
    # Deployments and StatefulSets only.
    experiment_target: TargetSupport | None
    # Newest first, at most 10.
    events: list[TopologyEvent]


class Provenance(BaseModel):
    # The API field the relationship was read from, e.g. "metadata.ownerReferences".
    source: str
    detail: str


class EdgeAttributes(BaseModel):
    """`endpoint` edges only: the endpoint's conditions."""

    ready: bool | None = None
    serving: bool | None = None
    terminating: bool | None = None


class TopologyEdge(BaseModel):
    # "<type>:<source id>-><target id>"
    id: str
    type: EdgeType
    source: str
    target: str
    provenance: Provenance
    attributes: EdgeAttributes


class TopologyUnknown(BaseModel):
    type: UnknownType
    # The node it concerns, if any.
    subject: str | None
    resource: str | None
    namespace: str | None
    detail: str


class TopologyScope(BaseModel):
    namespaces: list[str] | None
    excluded_namespaces: list[str]


class Traffic(BaseModel):
    observed: Literal[False]
    detail: str


class Topology(BaseModel):
    schema_: Literal["autoresilience-topology/1"] = Field(alias="schema")
    observed_at: datetime
    cluster: ClusterRef
    scope: TopologyScope
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    unknowns: list[TopologyUnknown]
    counts: dict[str, int]
    traffic: Traffic
    # Set when this topology is an application's view.
    application_id: uuid.UUID | None = None


class ClusterList(BaseModel):
    items: list[ClusterRef]


class NamespaceInfo(BaseModel):
    name: str
    # None when the namespace could not be read.
    workloads: int | None
    access: Literal["readable", "forbidden", "error"]
    detail: str


class NamespaceList(BaseModel):
    cluster: ClusterRef
    # namespaces: the cluster's namespace list; workloads: derived from workloads
    # (the engine may not list namespaces); configured: DISCOVERY_CLUSTERS.
    source: Literal["namespaces", "workloads", "configured"]
    items: list[NamespaceInfo]
    excluded_namespaces: list[str]
