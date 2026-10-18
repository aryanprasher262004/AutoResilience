import { act, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { endTour, useActiveTour } from "@/components/tour/tour-state";

import { mockApi, proxyDown } from "@/test/api";
import { dashboard, environment, ready, services } from "@/test/fixtures";
import { setUrl } from "@/test/navigation";
import { renderWithApi } from "@/test/render";

import { Diagnostics } from "./diagnostics";
import { HelpButton } from "./help-panel";
import { SetupChecklist } from "./setup-checklist";

describe("Setup checklist", () => {
  test("reports live progress from the API", async () => {
    mockApi().on("GET", "/ready", ready()).on("GET", "/services", services()).on("GET", "/dashboard/summary", dashboard());
    renderWithApi(<SetupChecklist />);
    const item = (label: string) => within(screen.getByText(label).closest("li")!);
    expect(await item("Engine API reachable and ready").findByText("Done")).toBeInTheDocument();
    expect(await item("Workloads discovered in the cluster").findByText(`${services().items.length} found`)).toBeInTheDocument();
    expect(await item("First experiment run").findByText(`${dashboard().total} recorded`)).toBeInTheDocument();
  });

  test("points to the matching fix when the API is unreachable", async () => {
    mockApi().on("GET", "/ready", proxyDown).on("GET", "/services", proxyDown).on("GET", "/dashboard/summary", proxyDown);
    renderWithApi(<SetupChecklist />);
    const item = within(screen.getByText("Engine API reachable and ready").closest("li")!);
    expect(await item.findByText("Unreachable")).toBeInTheDocument();
    expect(item.getByRole("link", { name: "See the fix below" })).toHaveAttribute("href", "#api-unreachable");
  });
});

describe("Diagnostics", () => {
  test("copies a secret-free summary", async () => {
    mockApi().on("GET", "/ready", ready()).on("GET", "/environment", environment());
    const { user } = renderWithApi(<Diagnostics upstream="http://localhost:8000" />);

    const text = screen.getByLabelText("Diagnostics");
    await vi.waitFor(() => expect(text).toHaveTextContent('"status":"ready"'));
    expect(text).toHaveTextContent("runtime mode: local");
    expect(text).toHaveTextContent("browser endpoint: /api/backend -> http://localhost:8000");
    expect(text).toHaveTextContent(
      "GET /environment: local-stack, context kind-autoresilience, database=pass kubernetes=pass prometheus=pass",
    );

    await user.click(screen.getByRole("button", { name: "Copy diagnostics" }));
    const copied = await navigator.clipboard.readText(); // user-event's clipboard
    expect(copied).toBe(text.textContent);
    expect(copied).toContain("GET /ready:");
    expect(copied).not.toMatch(/token|password|kubeconfig/i);
    expect(screen.getByRole("status")).toHaveTextContent("Copied");
  });
});

describe("Help panel", () => {
  afterEach(() => act(() => endTour()));

  test("? opens help for the current page, but not while typing", async () => {
    setUrl("/applications/7d2f");
    const { user } = renderWithApi(
      <>
        <input aria-label="Search" />
        <HelpButton />
      </>,
    );
    await user.type(screen.getByLabelText("Search"), "?");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(document.body);
    await user.keyboard("?");
    const panel = within(screen.getByRole("dialog", { name: "Application topology" }));
    expect(panel.getByText("Lines are relationships, not traffic")).toBeInTheDocument();
    expect(panel.getByRole("link", { name: /Topology contract/ })).toHaveAttribute("href", expect.stringContaining("docs/topology.md"));
  });

  test("starts the page's tour and closes", async () => {
    setUrl("/settings");
    const { user } = renderWithApi(
      <>
        <HelpButton />
        <TourProbe />
      </>,
    );
    await user.click(screen.getByRole("button", { name: "Help" }));
    await user.click(screen.getByRole("button", { name: "Take the tour" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("tour settings")).toBeInTheDocument();
  });
});

function TourProbe() {
  const tour = useActiveTour();
  return <p>tour {tour ? tour.page : "closed"}</p>;
}
