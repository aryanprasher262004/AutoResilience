/**
 * Contract-typed topology payloads, shaped after GET /topology on the kind cluster
 * (shop/checkout). The engine builds these; fixtures never add relationships it would not.
 */
import type {
  Application,
  ClusterRef,
  NamespaceList,
  Topology,
  TopologyEdge,
  TopologyNode,
} from "@/lib/api/types";

export const T = "2026-10-18T12:00:00Z";

export const EXECUTION: ClusterRef = {
  context: "kind-autoresilience",
  role: "execution",
  chaos_permitted: true,
  namespaces: null,
};
export const DISCOVERY: ClusterRef = {
  context: "kind-staging",
  role: "discovery",
  chaos_permitted: false,
  namespaces: ["shop", "payments"],
};

function node(kind: TopologyNode["kind"], name: string, overrides: Partial<TopologyNode> = {}): TopologyNode {
  const namespace = kind === "Node" ? null : "shop";
  return {
    id: namespace ? `${kind}:${namespace}/${name}` : `${kind}:${name}`,
    kind,
    namespace,
    name,
    uid: `uid-${name}`,
    labels: {},
    created_at: T,
    health: "HEALTHY",
    health_reason: "",
    replicas: null,
    pod: null,
    service: null,
    endpoint_slice: null,
    node: null,
    experiment_target: null,
    events: [],
    ...overrides,
  };
}

const replicas = (desired: number, ready: number) => ({
  desired,
  current: desired,
  ready,
  available: ready,
  updated: desired,
  selector: "app=checkout",
  revision: null,
});

const pod = (name: string, ready: boolean) =>
  node("Pod", name, {
    labels: { app: "checkout" },
    health: ready ? "HEALTHY" : "DEGRADED",
    health_reason: ready ? "Running and Ready" : "Running, not Ready",
    pod: {
      phase: "Running",
      ready,
      terminating: false,
      restarts: ready ? 0 : 4,
      node_name: "autoresilience-control-plane",
      pod_ip: "10.244.0.10",
      start_time: T,
      containers: [
        { name: "podinfo", image: "podinfo:6", ready, restart_count: ready ? 0 : 4, state: ready ? "running" : "waiting", reason: ready ? null : "CrashLoopBackOff" },
      ],
    },
  });

function edge(type: TopologyEdge["type"], source: string, target: string, source_field: string, ready?: boolean): TopologyEdge {
  return {
    id: `${type}:${source}->${target}`,
    type,
    source,
    target,
    provenance: { source: source_field, detail: `${type} from ${source_field}` },
    attributes: ready === undefined ? {} : { ready, serving: ready, terminating: false },
  };
}

export function topology(cluster: ClusterRef = EXECUTION, overrides: Partial<Topology> = {}): Topology {
  const target = cluster.chaos_permitted
    ? { supported: true, reason: "Supported kind on the execution cluster; safety validation decides whether an experiment may run." }
    : { supported: false, reason: "Read-only discovery cluster: chaos execution is not granted here." };
  const nodes = [
    node("Service", "checkout", {
      health: "DEGRADED",
      health_reason: "1/2 endpoints ready",
      service: { type: "ClusterIP", cluster_ip: "10.96.0.20", selector: { app: "checkout" }, ports: [{ name: "http", port: 80, target_port: "9898", protocol: "TCP" }] },
    }),
    node("Service", "legacy-db", { health: "UNKNOWN", service: { type: "ClusterIP", cluster_ip: null, selector: null, ports: [] } }),
    node("EndpointSlice", "checkout-abc", {
      health: "DEGRADED",
      endpoint_slice: { address_type: "IPv4", endpoints: 2, ready: 1, ports: [{ name: "http", port: 9898, protocol: "TCP" }] },
    }),
    node("Deployment", "checkout", {
      health: "DEGRADED",
      health_reason: "1/2 ready (controller status)",
      replicas: replicas(2, 1),
      experiment_target: target,
      events: [{ type: "Warning", reason: "Unhealthy", message: "Readiness probe failed", count: 3, last_seen: T }],
    }),
    node("ReplicaSet", "checkout-7d9", { replicas: { ...replicas(2, 1), revision: "2" }, health: "DEGRADED" }),
    node("ReplicaSet", "checkout-5c4", { replicas: { ...replicas(0, 0), revision: "1" }, health: "SCALED_TO_ZERO" }),
    pod("checkout-7d9-a", true),
    pod("checkout-7d9-b", false),
    node("Node", "autoresilience-control-plane", {
      node: { ready: "True", roles: ["control-plane"], unschedulable: false, kubelet_version: "v1.33.1", os_image: "Debian", architecture: "arm64" },
    }),
  ];
  const D = "Deployment:shop/checkout";
  const RS = "ReplicaSet:shop/checkout-7d9";
  const PA = "Pod:shop/checkout-7d9-a";
  const PB = "Pod:shop/checkout-7d9-b";
  const SVC = "Service:shop/checkout";
  const SLICE = "EndpointSlice:shop/checkout-abc";
  const NODE = "Node:autoresilience-control-plane";
  return {
    schema: "autoresilience-topology/1",
    observed_at: T,
    cluster,
    scope: { namespaces: ["shop"], excluded_namespaces: ["kube-system"] },
    nodes,
    edges: [
      edge("owns", D, RS, "metadata.ownerReferences"),
      edge("owns", D, "ReplicaSet:shop/checkout-5c4", "metadata.ownerReferences"),
      edge("owns", RS, PA, "metadata.ownerReferences"),
      edge("owns", RS, PB, "metadata.ownerReferences"),
      edge("owns", SVC, SLICE, "metadata.ownerReferences"),
      edge("selects", SVC, PA, "spec.selector"),
      edge("selects", SVC, PB, "spec.selector"),
      edge("endpoint", SLICE, PA, "endpoints.targetRef", true),
      edge("endpoint", SLICE, PB, "endpoints.targetRef", false),
      edge("scheduled_on", PA, NODE, "spec.nodeName"),
      edge("scheduled_on", PB, NODE, "spec.nodeName"),
    ],
    unknowns: [
      {
        type: "service_without_selector",
        subject: "Service:shop/legacy-db",
        resource: null,
        namespace: null,
        detail: "No spec.selector: its endpoints are managed outside Kubernetes selectors",
      },
      { type: "listing_forbidden", subject: null, resource: "nodes", namespace: null, detail: "Not permitted to list nodes (403)" },
    ],
    counts: { Service: 2, EndpointSlice: 1, Deployment: 1, ReplicaSet: 2, Pod: 2, Node: 1 },
    traffic: { observed: false, detail: "Edges are relationships declared in the Kubernetes API, not measured traffic." },
    application_id: null,
    ...overrides,
  };
}

export const APP_ID = "0b6d3c38-8e3e-4a43-9a3c-6c1f9f1a2b11";

export function application(overrides: Partial<Application> = {}): Application {
  return {
    id: APP_ID,
    name: "Shop",
    context: "kind-autoresilience",
    namespaces: ["shop"],
    cluster: EXECUTION,
    created_at: T,
    updated_at: T,
    ...overrides,
  };
}

export function namespaces(cluster: ClusterRef = EXECUTION, overrides: Partial<NamespaceList> = {}): NamespaceList {
  return {
    cluster,
    source: cluster.role === "execution" ? "namespaces" : "configured",
    items:
      cluster.role === "execution"
        ? [
            { name: "default", workloads: 0, access: "readable", detail: "0 workloads" },
            { name: "shop", workloads: 4, access: "readable", detail: "4 workloads" },
          ]
        : [
            { name: "shop", workloads: 1, access: "readable", detail: "1 workloads" },
            { name: "payments", workloads: null, access: "forbidden", detail: "Kubernetes API error 403" },
          ],
    excluded_namespaces: ["kube-system", "monitoring"],
    ...overrides,
  };
}
