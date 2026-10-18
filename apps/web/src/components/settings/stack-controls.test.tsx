import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { apiError, json, mockApi, networkError } from "@/test/api";
import { renderWithApi } from "@/test/render";

import { StackControls } from "./stack-controls";

const STATUS = {
  installed: true,
  docker: "running",
  cluster: { running: true },
  services: { postgres: { state: "running", health: "healthy" }, api: { state: "running", health: "healthy" }, web: { state: "running", health: "healthy" } },
  api: { ready_http: 200 },
  console: { reachable: true },
};
const OPS = { items: [{ name: "backup", title: "Back up experiment data", plan: ["pg_dump …"] }] };

function manager() {
  return mockApi().on("GET", "/v1/status", STATUS).on("GET", "/v1/operations", OPS);
}

describe("StackControls", () => {
  beforeEach(() => sessionStorage.clear());

  it("pairs with the loopback manager using the token, then shows status", async () => {
    const api = manager();
    const { user } = renderWithApi(<StackControls />);
    await user.type(screen.getByLabelText("Pairing token"), "tok-123");
    await user.click(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByRole("button", { name: "Back up experiment data" })).toBeInTheDocument();
    const [request] = api.requests("GET", "/v1/status");
    expect(request.url.origin).toBe("http://127.0.0.1:8765"); // direct to loopback, not via the API proxy
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/v1/status",
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer tok-123" }) }),
    );
    expect(JSON.parse(sessionStorage.getItem("autoresilience.manager")!)).toEqual({ port: 8765, token: "tok-123" });
  });

  it("runs an operation only after showing the manager's plan and confirming", async () => {
    sessionStorage.setItem("autoresilience.manager", JSON.stringify({ port: 8765, token: "t" }));
    let polls = 0;
    const api = manager()
      .on("POST", "/v1/operations/backup/plan", {
        operation: "backup",
        title: "Back up experiment data",
        plan: ["pg_dump of the stack database to ~/.autoresilience/backups"],
        confirmation: "c-1",
        expires_in_seconds: 120,
      })
      .on("POST", "/v1/operations/backup", () => json({ id: "j1", operation: "backup", state: "running", output: [], started_at: 1, finished_at: null }, 202))
      .on("GET", "/v1/jobs/j1", () =>
        json({ id: "j1", operation: "backup", state: polls++ ? "succeeded" : "running", output: ["Backup written"], started_at: 1, finished_at: 2 }),
      );
    const { user } = renderWithApi(<StackControls />);
    await user.click(await screen.findByRole("button", { name: "Back up experiment data" }));

    const dialog = within(screen.getByRole("dialog", { hidden: true }));
    expect(await dialog.findByText(/pg_dump of the stack database/)).toBeInTheDocument();
    expect(api.requests("POST", "/v1/operations/backup")).toHaveLength(0);
    await user.click(dialog.getByRole("button", { name: "Confirm and run", hidden: true }));
    await waitFor(() => expect(dialog.getByText("succeeded")).toBeInTheDocument(), { timeout: 4000 });
    expect(api.requests("POST", "/v1/operations/backup")[0].body).toEqual({ confirmation: "c-1" });
  });

  it("explains how to start the manager when nothing answers", async () => {
    mockApi().on("GET", "/v1/status", networkError).on("GET", "/v1/operations", networkError);
    const { user } = renderWithApi(<StackControls />);
    await user.type(screen.getByLabelText("Pairing token"), "x");
    await user.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("python3 tools/ar/ar.py manager");
  });

  it("forgets a rejected token", async () => {
    sessionStorage.setItem("autoresilience.manager", JSON.stringify({ port: 8765, token: "old" }));
    mockApi().on("GET", "/v1/status", () => apiError(401, "Pairing token missing or wrong")).on("GET", "/v1/operations", OPS);
    renderWithApi(<StackControls />);
    await waitFor(() => expect(sessionStorage.getItem("autoresilience.manager")).toBeNull());
    expect(screen.getByLabelText("Pairing token")).toBeInTheDocument();
  });
});
