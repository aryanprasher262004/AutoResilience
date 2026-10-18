/**
 * Presentation of the topology contract (`autoresilience-topology/1`, docs/topology.md).
 * Pure: filtering, a deterministic layered layout and relation lookups. Nothing here adds
 * nodes or edges; it only hides, groups and positions what the engine returned.
 */
import type { Tone } from "@/components/ui/badge";

import type { EdgeType, NodeHealth, NodeKind, Topology, TopologyEdge, TopologyNode } from "./api/types";

export const KIND_META: Record<NodeKind, { label: string; plural: string; column: number }> = {
  Service: { label: "Service", plural: "Services", column: 0 },
  EndpointSlice: { label: "EndpointSlice", plural: "EndpointSlices", column: 1 },
  Deployment: { label: "Deployment", plural: "Deployments", column: 2 },
  StatefulSet: { label: "StatefulSet", plural: "StatefulSets", column: 2 },
  ReplicaSet: { label: "ReplicaSet", plural: "ReplicaSets", column: 3 },
  Pod: { label: "Pod", plural: "Pods", column: 4 },
  Node: { label: "Node", plural: "Nodes", column: 5 },
};
export const KINDS = Object.keys(KIND_META) as NodeKind[];

export const EDGE_META: Record<EdgeType, { label: string; description: string }> = {
  owns: { label: "owns", description: "Controller owner reference (metadata.ownerReferences, UID verified)" },
  selects: { label: "selects", description: "Service selector matches the Pod's labels" },
  endpoint: { label: "endpoint", description: "EndpointSlice endpoint targets the Pod (targetRef, UID verified)" },
  slice_for: { label: "slice for", description: "EndpointSlice labelled kubernetes.io/service-name" },
  scheduled_on: { label: "runs on", description: "Pod spec.nodeName" },
};
export const EDGE_TYPES = Object.keys(EDGE_META) as EdgeType[];

export const NODE_HEALTH_META: Record<NodeHealth, { label: string; tone: Tone }> = {
  HEALTHY: { label: "Healthy", tone: "success" },
  DEGRADED: { label: "Degraded", tone: "warning" },
  UNAVAILABLE: { label: "Unavailable", tone: "danger" },
  SCALED_TO_ZERO: { label: "Scaled to zero", tone: "neutral" },
  COMPLETED: { label: "Completed", tone: "info" },
  UNKNOWN: { label: "Unknown", tone: "neutral" },
};

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
