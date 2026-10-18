import { screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { mockApi, proxyDown } from "@/test/api";
import { environment } from "@/test/fixtures";
import { renderWithApi } from "@/test/render";

import { LocalEnvironment, StackCommands } from "./local-environment";

const check = (label: string) =>
  within(within(screen.getByRole("list", { name: "Environment checks" })).getByText(label).closest("li")!);

describe("Local environment", () => {
  test("shows what the engine reports, check by check", async () => {
    mockApi().on("GET", "/environment", environment());
    renderWithApi(<LocalEnvironment />);

    expect(await screen.findByText("Local stack (containers managed by ar)")).toBeInTheDocument();
    expect(screen.getByText("kind-autoresilience")).toBeInTheDocument();
    for (const label of ["Database", "Cluster (Kubernetes API)", "Prometheus"]) {
      expect(check(label).getByText("Connected")).toBeInTheDocument();
    }
    expect(screen.getByText("6 workloads visible via context kind-autoresilience")).toBeInTheDocument();
  });

  test("failing checks get the fix for this runtime mode", async () => {
    const env = environment();
    env.checks[1] = { name: "kubernetes", status: "fail", detail: "Cannot list workloads via context kind-autoresilience: Kubernetes API error 403: Forbidden" };
    mockApi().on("GET", "/environment", env);
    renderWithApi(<LocalEnvironment />);

    await screen.findByText("Cluster (Kubernetes API)");
    const item = check("Cluster (Kubernetes API)");
    expect(item.getByText("Failing")).toBeInTheDocument();
    expect(item.getByText(/403: Forbidden/)).toBeInTheDocument();
    expect(item.getByText("python3 tools/ar/ar.py install")).toBeInTheDocument();
    expect(check("Database").queryByText(/ar\.py/)).toBeNull();
  });

  test("development mode names the current-context fallback and dev scripts", async () => {
    const env = environment({ runtime_mode: "development", kube_context: null });
    env.checks[2] = { name: "prometheus", status: "fail", detail: "http://localhost:9090: Prometheus unreachable" };
    mockApi().on("GET", "/environment", env);
    renderWithApi(<LocalEnvironment />);

    expect(await screen.findByText("Development (host processes)")).toBeInTheDocument();
    expect(screen.getByText(/current context \(development only\)/)).toBeInTheDocument();
    expect(check("Prometheus").getByText("./scripts/dev-cluster.sh")).toBeInTheDocument();
  });

  test("an unreachable engine is reported, not guessed, and re-check asks again", async () => {
    const api = mockApi().on("GET", "/environment", proxyDown);
    const { user } = renderWithApi(<LocalEnvironment />);

    expect(await screen.findByText("Engine unreachable")).toBeInTheDocument();
    expect(screen.queryByText("Connected")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Re-check" }));
    await screen.findByRole("button", { name: "Re-check" });
    expect(api.requests("GET", "/environment").length).toBeGreaterThanOrEqual(2);
  });

  test("stack management is documented, not offered as buttons", () => {
    renderWithApi(<StackCommands />);
    expect(screen.getByText("ar uninstall")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
