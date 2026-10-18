/**
 * Presentation of the topology contract (`autoresilience-topology/1`, docs/topology.md).
 * Pure: filtering, a deterministic layered layout and relation lookups. Nothing here adds
 * nodes or edges; it only hides, groups and positions what the engine returned.
 */
import type { Tone } from "@/components/ui/badge";

import type { EdgeType, NodeHealth, NodeKind, Topology, TopologyEdge, TopologyNode, TopologyUnknown } from "./api/types";

export const KIND_META: Record<NodeKind, { label: string; plural: string; column: number; description: string }> = {
  Service: { label: "Service", plural: "Services", column: 0, description: "A stable network name for a set of Pods, chosen by its label selector." },
  EndpointSlice: {
    label: "EndpointSlice",
    plural: "EndpointSlices",
    column: 1,
    description: "The Pod addresses a Service currently routes to, with each endpoint's readiness.",
  },
  Deployment: { label: "Deployment", plural: "Deployments", column: 2, description: "Keeps a number of identical Pods running through ReplicaSets. Can be an experiment target." },
  StatefulSet: { label: "StatefulSet", plural: "StatefulSets", column: 2, description: "Pods with stable names and storage, replaced one by one. Can be an experiment target." },
  ReplicaSet: { label: "ReplicaSet", plural: "ReplicaSets", column: 3, description: "One revision of a Deployment; it creates that revision's Pods." },
  Pod: { label: "Pod", plural: "Pods", column: 4, description: "A running instance of the workload's containers. pod-delete removes these." },
  Node: { label: "Node", plural: "Nodes", column: 5, description: "A cluster machine the Pods are scheduled on (shown only if the engine may read Nodes)." },
};
export const KINDS = Object.keys(KIND_META) as NodeKind[];

/** How each kind's health is read (docs/topology.md); nothing is estimated. */
export const HEALTH_SOURCE: Record<NodeKind, string> = {
  Deployment: "Read from the controller's ready and desired replicas.",
  StatefulSet: "Read from the controller's ready and desired replicas.",
  ReplicaSet: "Read from the controller's ready and desired replicas.",
  Pod: "Read from the Pod's phase and Ready condition.",
  Service: "Read from the ready endpoints of its EndpointSlices.",
  EndpointSlice: "Read from its endpoints' ready condition.",
  Node: "Read from the Node's Ready condition.",
};

/**
 * Relationship types. Every one is read from the Kubernetes API and verified as stated;
 * none is runtime traffic. `stroke`/`dash` are shared by the graph and its legend.
 */
export const EDGE_META: Record<
  EdgeType,
  { label: string; description: string; verified: string; stroke: string; dash?: string }
> = {
  owns: {
    label: "owns",
    description: "Controller owner reference (metadata.ownerReferences, UID verified)",
    verified: "The owner's UID matches the object that was read.",
    stroke: "var(--color-line-strong)",
  },
  selects: {
    label: "selects",
    description: "Service selector matches the Pod's labels",
    verified: "Every selector label equals the Pod's, in the same namespace.",
    stroke: "var(--color-accent)",
    dash: "6 4",
  },
  endpoint: {
    label: "endpoint",
    description: "EndpointSlice endpoint targets the Pod (targetRef, UID verified)",
    verified: "The endpoint's targetRef names the Pod's UID. Amber when the endpoint is not ready.",
    stroke: "var(--color-success)",
    dash: "2 4",
  },
  slice_for: {
    label: "slice for",
    description: "EndpointSlice labelled kubernetes.io/service-name",
    verified: "The named Service was read.",
    stroke: "var(--color-line-strong)",
    dash: "2 4",
  },
  scheduled_on: {
    label: "runs on",
    description: "Pod spec.nodeName",
    verified: "The named Node was read.",
    stroke: "var(--color-faint)",
    dash: "8 6",
  },
};
export const EDGE_TYPES = Object.keys(EDGE_META) as EdgeType[];

export const NODE_HEALTH_META: Record<NodeHealth, { label: string; tone: Tone; description: string }> = {
  HEALTHY: { label: "Healthy", tone: "success", description: "Everything the object reports is ready." },
  DEGRADED: { label: "Degraded", tone: "warning", description: "Partly ready, for example 1 of 2 replicas." },
  UNAVAILABLE: { label: "Unavailable", tone: "danger", description: "Nothing ready, or the Pod failed." },
  SCALED_TO_ZERO: { label: "Scaled to zero", tone: "neutral", description: "Zero replicas desired." },
  COMPLETED: { label: "Completed", tone: "info", description: "A Pod that ran to completion." },
  UNKNOWN: { label: "Unknown", tone: "neutral", description: "The status could not be read." },
};

/** Why something is listed as not verified (docs/topology.md, "Unknowns"). */
export const UNKNOWN_META: Record<TopologyUnknown["type"], string> = {
  listing_forbidden: "The engine's identity may not list this resource here (401/403).",
  listing_failed: "Listing this resource failed for another reason.",
  listing_truncated: "More objects than one listing returns; the rest are not shown.",
  owner_not_observed: "Owned by a kind the topology does not list (Job, DaemonSet, custom resource) or by an object that was not found.",
  owner_uid_mismatch: "The named owner exists but with another UID, so it was recreated; no relationship is drawn.",
  node_not_observed: "Scheduled on a Node that is absent or not readable.",
  service_without_selector: "A Service without a selector (or ExternalName): no Pods are linked by selector.",
  endpoint_target_not_observed: "An endpoint targets a Pod that is gone, out of scope, or not a Pod.",
  malformed_object: "An object without a name or namespace was skipped.",
};

/** Health dot colour per badge tone, shared by the graph and the legend. */
export const TONE_DOT: Record<Tone, string> = {
  fault: "bg-fault",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
  neutral: "bg-faint",
};

/**
 * What a topology renderer receives. The 2D graph implements it; a later 3D renderer
 * (docs/topology.md, "Views") takes the same props, so filtering, selection, the
 * inspector and the contract stay shared and renderers only draw.
 */
export type TopologyRendererProps = {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  selected: string | null;
  /** Node ids matching the search; others are dimmed. Null: no search. */
  matches: Set<string> | null;
  onSelect: (id: string | null) => void;
};

/**
 * What stays bright when `id` is selected: itself, everything directly related to it by a
 * visible edge, and its whole owner chain (a Deployment's ReplicaSets and Pods, a Pod's
 * owners), so selecting a workload shows the workload.
 */
export function neighbourhood(edges: TopologyEdge[], id: string): Set<string> {
  const ids = new Set([id]);
  for (const e of edges) {
    if (e.source === id) ids.add(e.target);
    if (e.target === id) ids.add(e.source);
  }
  const owns = edges.filter((e) => e.type === "owns");
  for (const [from, to] of [["source", "target"], ["target", "source"]] as const) {
    const queue = [id];
    const seen = new Set(queue);
    while (queue.length) {
      const current = queue.shift()!;
      for (const e of owns) {
        if (e[from] === current && !seen.has(e[to])) {
          seen.add(e[to]);
          ids.add(e[to]);
          queue.push(e[to]);
        }
      }
    }
  }
  return ids;
}

export type TopologyFilter = {
  kinds: NodeKind[];
  edges: EdgeType[];
  namespace: string; // "" for all
  search: string;
  /** ReplicaSets with 0 desired replicas (old Deployment revisions). */
  inactiveReplicaSets: boolean;
};

export const DEFAULT_FILTER: TopologyFilter = {
  kinds: KINDS,
  edges: EDGE_TYPES,
  namespace: "",
  search: "",
  inactiveReplicaSets: false,
};

export function isInactiveReplicaSet(node: TopologyNode): boolean {
  return node.kind === "ReplicaSet" && node.replicas?.desired === 0;
}

export function matchesSearch(node: TopologyNode, search: string): boolean {
  const q = search.trim().toLowerCase();
  if (!q) return true;
  return `${node.kind} ${node.namespace ?? ""}/${node.name}`.toLowerCase().includes(q);
}

/** Visible nodes and the edges between them. Cluster Nodes follow their Pods' namespace. */
export function applyFilter(topology: Topology, filter: TopologyFilter) {
  const kinds = new Set(filter.kinds);
  const edgeTypes = new Set(filter.edges);
  const namespaced = topology.nodes.filter(
    (n) =>
      n.namespace !== null &&
      kinds.has(n.kind) &&
      (!filter.namespace || n.namespace === filter.namespace) &&
      (filter.inactiveReplicaSets || !isInactiveReplicaSet(n)),
  );
  const ids = new Set(namespaced.map((n) => n.id));
  // A cluster Node is shown if a visible Pod runs on it (or no namespace filter applies).
  const hosts = new Set(
    topology.edges.filter((e) => e.type === "scheduled_on" && ids.has(e.source)).map((e) => e.target),
  );
  const clusterNodes = topology.nodes.filter(
    (n) => n.namespace === null && kinds.has(n.kind) && (!filter.namespace || hosts.has(n.id)),
  );
  const nodes = [...namespaced, ...clusterNodes];
  const visible = new Set(nodes.map((n) => n.id));
  const edges = topology.edges.filter(
    (e) => edgeTypes.has(e.type) && visible.has(e.source) && visible.has(e.target),
  );
  return { nodes, edges };
}

export const NODE_WIDTH = 188;
export const NODE_HEIGHT = 46;
const COLUMN_GAP = 56;
const ROW_HEIGHT = 58;
const GROUP_PADDING = 20;
const GROUP_HEADER = 30;
const GROUP_GAP = 36;

export type Positioned = { id: string; x: number; y: number };
export type Group = { id: string; label: string; x: number; y: number; width: number; height: number; members: Positioned[] };

/**
 * Top-level owner of each node (Deployment/StatefulSet, else itself), used to keep a
 * workload's ReplicaSets, Pods, Services and slices on the same rows.
 */
function anchors(nodes: TopologyNode[], edges: TopologyEdge[]): Map<string, string> {
  const owner = new Map<string, string>();
  for (const e of edges) if (e.type === "owns") owner.set(e.target, e.source);
  const top = (id: string) => {
    let current = id;
    for (let i = 0; i < 4 && owner.has(current); i++) current = owner.get(current)!;
    return current;
  };
  const result = new Map(nodes.map((n) => [n.id, top(n.id)]));
  // Services (and their slices) sit next to the workload of the first Pod they select.
  for (const e of [...edges].sort((a, b) => a.id.localeCompare(b.id))) {
    if (e.type === "selects" && result.get(e.source) === e.source) result.set(e.source, result.get(e.target) ?? e.source);
  }
  for (const n of nodes) {
    if (n.kind === "EndpointSlice") {
      const svc = result.get(owner.get(n.id) ?? "");
      if (svc) result.set(n.id, svc);
    }
  }
  return result;
}

/** Deterministic layered layout: one group per namespace (plus cluster Nodes), kinds as columns. */
export function layout(nodes: TopologyNode[], edges: TopologyEdge[]): Group[] {
  const anchorOf = anchors(nodes, edges);
  const byGroup = new Map<string, TopologyNode[]>();
  for (const n of nodes) {
    const key = n.namespace ?? "";
    byGroup.set(key, [...(byGroup.get(key) ?? []), n]);
  }
  const groups: Group[] = [];
  let y = 0;
  const keys = [...byGroup.keys()].sort((a, b) => (a === "" ? 1 : b === "" ? -1 : a.localeCompare(b)));
  for (const key of keys) {
    const members = byGroup.get(key)!;
    const columns = [...new Set(members.map((n) => KIND_META[n.kind].column))].sort((a, b) => a - b);
    const columnIndex = new Map(columns.map((c, i) => [c, i]));
    // Families (by anchor) in name order; each family is as tall as its tallest column.
    const families = new Map<string, TopologyNode[]>();
    for (const n of members) {
      const anchor = anchorOf.get(n.id) ?? n.id;
      families.set(anchor, [...(families.get(anchor) ?? []), n]);
    }
    const familyOrder = [...families.keys()].sort((a, b) => {
      const name = (id: string) => id.split("/").pop() ?? id;
      return name(a).localeCompare(name(b)) || a.localeCompare(b);
    });
    const positioned: Positioned[] = [];
    let row = 0;
    for (const anchor of familyOrder) {
      const perColumn = new Map<number, TopologyNode[]>();
      for (const n of families.get(anchor)!) {
        const c = KIND_META[n.kind].column;
        perColumn.set(c, [...(perColumn.get(c) ?? []), n]);
      }
      let height = 1;
      for (const [column, list] of perColumn) {
        list.sort((a, b) => a.name.localeCompare(b.name));
        list.forEach((n, i) =>
          positioned.push({
            id: n.id,
            x: GROUP_PADDING + columnIndex.get(column)! * (NODE_WIDTH + COLUMN_GAP),
            y: GROUP_HEADER + (row + i) * ROW_HEIGHT,
          }),
        );
        height = Math.max(height, list.length);
      }
      row += height;
    }
    positioned.sort((a, b) => a.id.localeCompare(b.id));
    const width = GROUP_PADDING * 2 + columns.length * NODE_WIDTH + (columns.length - 1) * COLUMN_GAP;
    const height = GROUP_HEADER + row * ROW_HEIGHT + GROUP_PADDING - (ROW_HEIGHT - NODE_HEIGHT);
    if (key) {
      groups.push({ id: `group:${key}`, label: `namespace ${key}`, x: 0, y, width, height, members: positioned });
      y += height + GROUP_GAP;
    } else {
      // Cluster Nodes sit to the right of every namespace, next to the Pod column.
      const right = Math.max(0, ...groups.map((g) => g.width));
      groups.push({ id: "group:cluster", label: "cluster nodes", x: right + GROUP_GAP, y: 0, width, height, members: positioned });
    }
  }
  return groups;
}

export type Relation = { edge: TopologyEdge; direction: "out" | "in"; other: TopologyNode | undefined };

export function relationsOf(topology: Topology, nodeId: string): Relation[] {
  const byId = new Map(topology.nodes.map((n) => [n.id, n]));
  return topology.edges
    .filter((e) => e.source === nodeId || e.target === nodeId)
    .map((edge) => {
      const out = edge.source === nodeId;
      return { edge, direction: out ? "out" : "in", other: byId.get(out ? edge.target : edge.source) } as Relation;
    });
}

export function unknownsOf(topology: Topology, nodeId: string) {
  return topology.unknowns.filter((u) => u.subject === nodeId);
}

export type WorkloadRow = {
  node: TopologyNode;
  pods: TopologyNode[];
  services: TopologyNode[];
  warnings: number;
};

/**
 * Deployments and StatefulSets with what the graph verifies about them: their Pods (via
 * owner references), the Services selecting those Pods, and Warning events on any of them.
 */
export function workloadRows(topology: Topology): WorkloadRow[] {
  const byId = new Map(topology.nodes.map((n) => [n.id, n]));
  const owned = new Map<string, string[]>();
  for (const e of topology.edges) if (e.type === "owns") owned.set(e.source, [...(owned.get(e.source) ?? []), e.target]);
  const descendants = (id: string): string[] => (owned.get(id) ?? []).flatMap((child) => [child, ...descendants(child)]);
  return topology.nodes
    .filter((n) => n.kind === "Deployment" || n.kind === "StatefulSet")
    .map((node) => {
      const family = descendants(node.id);
      const pods = family.map((id) => byId.get(id)!).filter((n) => n?.kind === "Pod");
      const podIds = new Set(pods.map((p) => p.id));
      const services = [
        ...new Set(topology.edges.filter((e) => e.type === "selects" && podIds.has(e.target)).map((e) => e.source)),
      ].map((id) => byId.get(id)!);
      const warnings = [node.id, ...family]
        .flatMap((id) => byId.get(id)?.events ?? [])
        .filter((e) => e.type === "Warning").length;
      return { node, pods, services, warnings };
    });
}
