import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithApi } from "@/test/render";
import { DISCOVERY, topology } from "@/test/topology-fixtures";

import { TopologyView } from "./topology-view";

// The canvas needs real layout measurement (no happy-dom support); the graph is
// exercised in the browser. Here it records what it is given and offers selection.
vi.mock("./topology-graph", () => ({
  TopologyGraph: ({ nodes, edges, onSelect }: { nodes: { id: string }[]; edges: unknown[]; onSelect: (id: string) => void }) => (
    <div data-testid="graph" data-nodes={nodes.length} data-edges={edges.length}>
      {nodes.map((n) => (
        <button key={n.id} type="button" onClick={() => onSelect(n.id)}>
          node {n.id}
        </button>
      ))}
    </div>
  ),
}));

describe("TopologyView", () => {
  it("passes filtered nodes and edges to the graph", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology()} />);
    const graph = screen.getByTestId("graph");
    expect(graph).toHaveAttribute("data-nodes", "8"); // inactive ReplicaSet hidden
    await user.click(screen.getByRole("button", { name: /^Pods/ }));
    expect(screen.getByRole("button", { name: /^Pods/ })).toHaveAttribute("aria-pressed", "false");
    expect(graph).toHaveAttribute("data-nodes", "6");
    await user.click(screen.getByRole("button", { name: "Inactive ReplicaSets" }));
    expect(graph).toHaveAttribute("data-nodes", "7");
  });

  it("inspects a workload: status, provenance, events and the builder hand-off", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology()} />);
    await user.click(screen.getByRole("button", { name: "node Deployment:shop/checkout" }));
    const inspector = within(screen.getByRole("complementary", { name: "Inspector" }));
    expect(inspector.getByText("1/2 ready (controller status)")).toBeInTheDocument();
    expect(inspector.getAllByText("metadata.ownerReferences").length).toBeGreaterThan(0);
    expect(inspector.getByText("Readiness probe failed")).toBeInTheDocument();
    expect(inspector.getByRole("link", { name: "New experiment" })).toHaveAttribute(
      "href",
      "/experiments/new?namespace=shop&kind=Deployment&name=checkout",
    );
    // Following a relationship selects the other node.
    await user.click(inspector.getByRole("button", { name: "ReplicaSet checkout-7d9" }));
    expect(within(screen.getByRole("complementary", { name: "Inspector" })).getByText("checkout-7d9")).toBeInTheDocument();
  });

  it("never offers experiments on a read-only discovery cluster", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology(DISCOVERY)} />);
    await user.click(screen.getByRole("button", { name: "node Deployment:shop/checkout" }));
    const inspector = within(screen.getByRole("complementary", { name: "Inspector" }));
    expect(inspector.queryByRole("link", { name: "New experiment" })).not.toBeInTheDocument();
    expect(inspector.getByText(/chaos execution is not granted/)).toBeInTheDocument();
  });

  it("offers an equivalent list view and shows unknowns instead of guessing", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology()} />);
    await user.click(screen.getByRole("button", { name: "List" }));
    expect(screen.queryByTestId("graph")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "checkout-7d9-b" }));
    expect(within(screen.getByRole("complementary", { name: "Inspector" })).getByText("CrashLoopBackOff")).toBeInTheDocument();

    await user.click(screen.getByText(/Not verified \(2\)/));
    expect(screen.getByText(/No spec.selector/)).toBeInTheDocument();
    expect(screen.getByText(/Not permitted to list nodes/)).toBeInTheDocument();
  });

  it("dims nothing away: search narrows the list but keeps the graph's context", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology()} />);
    await user.type(screen.getByRole("searchbox", { name: "Search resources" }), "legacy");
    expect(screen.getByTestId("graph")).toHaveAttribute("data-nodes", "8");
    await user.click(screen.getByRole("button", { name: "List" }));
    expect(screen.getAllByRole("row")).toHaveLength(2); // header + legacy-db
  });

  it("labels a stale snapshot when refreshing failed", () => {
    renderWithApi(<TopologyView topology={topology()} refreshError="503 Kubernetes API unreachable" />);
    expect(screen.getByRole("status")).toHaveTextContent("Showing an earlier snapshot");
    expect(screen.getByRole("status")).toHaveTextContent("503 Kubernetes API unreachable");
  });

  it("explains each resource kind and relationship in an accessible tooltip", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology()} />);
    const pods = screen.getByRole("button", { name: /^Pods/ });
    expect(pods).toHaveAccessibleDescription(/A running instance of the workload's containers/);
    const selects = within(screen.getByRole("group", { name: "Relationship types" })).getByRole("button", { name: "selects" });
    expect(selects).toHaveAccessibleDescription(/selector matches the Pod's labels.*not traffic/);

    const tooltip = document.getElementById(selects.getAttribute("aria-describedby")!)!;
    expect(tooltip).toHaveClass("hidden");
    await user.hover(selects);
    expect(tooltip).not.toHaveClass("hidden");
    await user.keyboard("{Escape}");
    expect(tooltip).toHaveClass("hidden");
  });

  it("has an expandable legend for kinds, health, relationships and marks", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology()} />);
    const summary = screen.getByText("Lines are relationships Kubernetes records, not measured traffic.");
    const legend = summary.closest("details")!;
    expect(legend).not.toHaveAttribute("open");
    await user.click(summary);
    expect(legend).toHaveAttribute("open");
    const content = within(legend);
    for (const heading of ["Resource kinds", "Health (dot colour)", "Relationships (lines)", "Marks and toggles"]) {
      expect(content.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(content.getByText("runs on")).toBeInTheDocument();
    expect(content.getByText(/listed below the graph, never drawn as a guess/)).toBeInTheDocument();
  });

  it("announces the selection, explains the inspector's sections and can clear it", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology()} />);
    const inspector = () => within(screen.getByRole("complementary", { name: "Inspector" }));
    expect(inspector().getByText("Nothing selected")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "node Deployment:shop/checkout" }));
    expect(screen.getByText(/^Selected Deployment checkout, \d+ relationships?\.$/)).toBeInTheDocument();
    expect(inspector().getByText(/Read from the controller's ready and desired replicas/)).toBeInTheDocument();
    expect(inspector().getByText(/Not measured traffic/)).toBeInTheDocument();
    expect(inspector().getByText(/opens the builder with this workload filled in/)).toBeInTheDocument();

    await user.click(inspector().getByRole("button", { name: "Clear selection" }));
    expect(inspector().getByText("Nothing selected")).toBeInTheDocument();
  });

  it("says which filters hide everything", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology()} />);
    const kinds = within(screen.getByRole("group", { name: "Resource kinds" }));
    for (const button of kinds.getAllByRole("button", { pressed: true })) await user.click(button);
    expect(screen.getByText("No resources match these filters")).toBeInTheDocument();
    expect(screen.getByText(/resource kinds are hidden/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByTestId("graph")).toHaveAttribute("data-nodes", "8");
  });

  it("explains each unverified item's type", async () => {
    const { user } = renderWithApi(<TopologyView topology={topology()} />);
    await user.click(screen.getByText(/Not verified \(2\)/));
    expect(screen.getByText(/A Service without a selector \(or ExternalName\)/)).toBeInTheDocument();
  });

  it("explains an empty scope", () => {
    renderWithApi(<TopologyView topology={topology(undefined, { nodes: [], edges: [], unknowns: [], counts: {} })} />);
    expect(screen.getByText("No resources in this scope")).toBeInTheDocument();
  });
});
