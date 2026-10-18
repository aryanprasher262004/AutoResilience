import { screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { mockApi, proxyDown } from "@/test/api";
import { dashboard, environment, ready, services } from "@/test/fixtures";
import { renderWithApi } from "@/test/render";

import { Diagnostics } from "./diagnostics";
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
