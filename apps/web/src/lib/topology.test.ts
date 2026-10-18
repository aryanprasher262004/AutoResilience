import { describe, expect, it } from "vitest";

import { topology } from "@/test/topology-fixtures";

import {
  DEFAULT_FILTER,
  NODE_HEIGHT,
  NODE_WIDTH,
  applyFilter,
  layout,
  relationsOf,
  workloadRows,
} from "./topology";

describe("applyFilter", () => {
  it("hides inactive ReplicaSets by default and only keeps edges between visible nodes", () => {
    const { nodes, edges } = applyFilter(topology(), DEFAULT_FILTER);
    expect(nodes.map((n) => n.id)).not.toContain("ReplicaSet:shop/checkout-5c4");
    expect(edges.every((e) => nodes.some((n) => n.id === e.source) && nodes.some((n) => n.id === e.target))).toBe(true);
    expect(edges.map((e) => e.id)).not.toContain("owns:Deployment:shop/checkout->ReplicaSet:shop/checkout-5c4");

    const all = applyFilter(topology(), { ...DEFAULT_FILTER, inactiveReplicaSets: true });
    expect(all.nodes).toHaveLength(topology().nodes.length);
  });

  it("filters kinds and edge types without inventing anything", () => {
    const { nodes, edges } = applyFilter(topology(), { ...DEFAULT_FILTER, kinds: ["Service", "Pod"], edges: ["selects"] });
    expect(new Set(nodes.map((n) => n.kind))).toEqual(new Set(["Service", "Pod"]));
    expect(edges.map((e) => e.type)).toEqual(["selects", "selects"]);
  });

  it("keeps a cluster Node only while one of its visible Pods runs on it", () => {
    expect(applyFilter(topology(), { ...DEFAULT_FILTER, namespace: "shop" }).nodes.map((n) => n.kind)).toContain("Node");
    expect(applyFilter(topology(), { ...DEFAULT_FILTER, namespace: "other" }).nodes).toEqual([]);
  });
});

describe("layout", () => {
  it("is deterministic, groups by namespace and never overlaps nodes", () => {
    const { nodes, edges } = applyFilter(topology(), DEFAULT_FILTER);
    const first = layout(nodes, edges);
    expect(layout([...nodes].reverse(), [...edges].reverse())).toEqual(first);
    expect(first.map((g) => g.label)).toEqual(["namespace shop", "cluster nodes"]);
    const boxes = first.flatMap((g) => g.members.map((m) => ({ x: g.x + m.x, y: g.y + m.y })));
    for (const [i, a] of boxes.entries())
      for (const b of boxes.slice(i + 1))
        expect(Math.abs(a.x - b.x) >= NODE_WIDTH || Math.abs(a.y - b.y) >= NODE_HEIGHT).toBe(true);
  });

  it("orders kinds left to right: Service, slice, workload, ReplicaSet, Pod", () => {
    const { nodes, edges } = applyFilter(topology(), DEFAULT_FILTER);
    const [shop] = layout(nodes, edges);
    const x = (id: string) => shop.members.find((m) => m.id === id)!.x;
    expect(x("Service:shop/checkout")).toBeLessThan(x("EndpointSlice:shop/checkout-abc"));
    expect(x("EndpointSlice:shop/checkout-abc")).toBeLessThan(x("Deployment:shop/checkout"));
    expect(x("Deployment:shop/checkout")).toBeLessThan(x("ReplicaSet:shop/checkout-7d9"));
    expect(x("ReplicaSet:shop/checkout-7d9")).toBeLessThan(x("Pod:shop/checkout-7d9-a"));
  });
});

describe("relations and workloads", () => {
  it("lists a node's edges in both directions", () => {
    const relations = relationsOf(topology(), "Pod:shop/checkout-7d9-b");
    expect(relations.map((r) => [r.edge.type, r.direction])).toEqual([
      ["owns", "in"],
      ["selects", "in"],
      ["endpoint", "in"],
      ["scheduled_on", "out"],
    ]);
  });

  it("derives workload rows only from ownership, selectors and events", () => {
    const [row] = workloadRows(topology());
    expect(row.node.name).toBe("checkout");
    expect(row.pods.map((p) => p.name)).toEqual(["checkout-7d9-a", "checkout-7d9-b"]);
    expect(row.services.map((s) => s.name)).toEqual(["checkout"]);
    expect(row.warnings).toBe(1);
  });
});
