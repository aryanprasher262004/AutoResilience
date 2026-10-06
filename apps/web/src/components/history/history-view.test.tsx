import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { apiError, json, mockApi, networkError } from "@/test/api";
import { ID, dashboard, page, summary } from "@/test/fixtures";
import { currentUrl, router, setUrl } from "@/test/navigation";
import { renderWithApi } from "@/test/render";

import { HistoryView } from "./history-view";

const COMPLETED = summary();
const BLOCKED = summary({
  id: "60cc030d-3ee3-4ed5-9b8f-7b73a7a7e30e",
  name: "coredns probe (blocked)",
  target: { namespace: "kube-system", kind: "Deployment", name: "coredns" },
  state: "VALIDATION_FAILED",
  has_baseline: false,
  score: null,
  time_to_recovery_seconds: null,
  client_outage_seconds: null,
  outcome_reason: "Namespace 'kube-system' is protected and cannot be targeted",
});

function setup(history: Parameters<ReturnType<typeof mockApi>["on"]>[2] = page([COMPLETED, BLOCKED])) {
  const api = mockApi().on("GET", "/dashboard/summary", dashboard()).on("GET", "/experiments/history", history);
  return { api, ...renderWithApi(<HistoryView mode="history" />) };
}

/** The query string of the most recent history request (what the backend filters on). */
function lastQuery(api: ReturnType<typeof mockApi>) {
  return api.requests("GET", "/experiments/history").at(-1)!.url.searchParams;
}

describe("Experiment history", () => {
  test("renders the API's rows: state, score, recovery, outcome and count", async () => {
    setUrl("/experiments");
    setup();

    const row = (await screen.findByText("fragile pod-delete graceful")).closest("tr")!;
    expect(within(row).getByText("Completed")).toBeInTheDocument();
    expect(within(row).getByText("83.9")).toBeInTheDocument();
    expect(within(row).getByText("10 s")).toBeInTheDocument();
    const blocked = screen.getByText("coredns probe (blocked)").closest("tr")!;
    expect(within(blocked).getByText("Validation failed")).toBeInTheDocument();
    expect(within(blocked).getAllByText("—").length).toBeGreaterThan(0); // no score, no recovery
    expect(screen.getByText("1–2 of 2")).toBeInTheDocument();
  });

  test("default request: newest first, first page of 25", async () => {
    setUrl("/experiments");
    const { api } = setup();
    await screen.findByText("fragile pod-delete graceful");

    const q = lastQuery(api);
    expect(Object.fromEntries(q)).toEqual({ sort: "created_at", order: "desc", limit: "25", offset: "0" });
  });

  test("search is debounced into the URL and sent to the backend", async () => {
    setUrl("/experiments");
    const { api, user } = setup();
    await screen.findByText("fragile pod-delete graceful");

    await user.type(screen.getByLabelText("Search"), "fragile");

    await waitFor(() => expect(lastQuery(api).get("q")).toBe("fragile"));
    expect(currentUrl().searchParams.get("q")).toBe("fragile");
    // One request for the final term, not one per keystroke.
    expect(api.requests("GET", "/experiments/history").filter((r) => r.url.searchParams.has("q"))).toHaveLength(1);
  });

  test("state, fault and namespace filters map onto the backend's filters", async () => {
    setUrl("/experiments");
    const { api, user } = setup();
    await screen.findByText("fragile pod-delete graceful");

    await user.selectOptions(screen.getByLabelText("State"), "Failed (validation / injection)");
    await waitFor(() => expect(lastQuery(api).getAll("state")).toEqual(["VALIDATION_FAILED", "INJECTION_FAILED"]));

    await user.selectOptions(screen.getByLabelText("Fault"), "pod-delete");
    await user.selectOptions(screen.getByLabelText("Namespace"), "shop (1)");
    await waitFor(() => {
      const q = lastQuery(api);
      expect(q.getAll("fault_type")).toEqual(["pod-delete"]);
      expect(q.getAll("namespace")).toEqual(["shop"]);
      expect(q.getAll("state")).toEqual(["VALIDATION_FAILED", "INJECTION_FAILED"]);
    });
    expect(currentUrl().search).toBe("?state=failed&fault=pod-delete&ns=shop");
  });

  test("sorting sends sort and order", async () => {
    setUrl("/experiments");
    const { api, user } = setup();
    await screen.findByText("fragile pod-delete graceful");

    await user.selectOptions(screen.getByLabelText("Sort"), "Score: high to low");

    await waitFor(() => expect(lastQuery(api).get("sort")).toBe("score"));
    expect(lastQuery(api).get("order")).toBe("desc");
    expect(currentUrl().searchParams.get("sort")).toBe("score_desc");
  });

  test("pagination requests the next offset and keeps the page in the URL", async () => {
    setUrl("/experiments");
    const { api, user } = setup(({ url }) => {
      const offset = Number(url.searchParams.get("offset"));
      return json(page([summary({ name: `run at offset ${offset}` })], 30, offset));
    });
    expect(await screen.findByText("1–1 of 30")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("run at offset 25")).toBeInTheDocument();
    expect(lastQuery(api).get("offset")).toBe("25");
    expect(currentUrl().searchParams.get("page")).toBe("2");
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  test("state in the URL (refresh / shared link) drives the first request and the controls", async () => {
    setUrl("/experiments?q=checkout&state=completed&ns=shop&sort=name&page=2");
    const { api } = setup(page([], 26, 25));
    await waitFor(() => expect(api.requests("GET", "/experiments/history")).toHaveLength(1));

    const q = lastQuery(api);
    expect(q.get("q")).toBe("checkout");
    expect(q.getAll("state")).toEqual(["COMPLETED"]);
    expect(q.getAll("namespace")).toEqual(["shop"]);
    expect([q.get("sort"), q.get("order"), q.get("offset")]).toEqual(["name", "asc", "25"]);
    expect(screen.getByLabelText("Search")).toHaveValue("checkout");
    expect(screen.getByLabelText("State")).toHaveValue("completed");
    expect(screen.getByLabelText("Sort")).toHaveValue("name");
  });

  test("row click opens the experiment room", async () => {
    setUrl("/experiments");
    const { user } = setup();

    await user.click((await screen.findByText("83.9")).closest("tr")!);

    expect(router.push).toHaveBeenCalledWith(`/experiments/${ID}`);
  });

  test("empty history vs. no matches", async () => {
    setUrl("/experiments");
    setup(page([]));
    expect(await screen.findByText("No experiments yet")).toBeInTheDocument();
  });

  test("no matches for active filters offers a reset", async () => {
    setUrl("/experiments?q=zzz");
    const { user } = setup(page([]));

    expect(await screen.findByText("No experiments match these filters")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(currentUrl().search).toBe("");
  });

  test.each([
    ["a backend error shows its detail", () => apiError(503, "Database unavailable at localhost:5432/autoresilience"), /503 Database unavailable at localhost:5432\/autoresilience/],
    ["an unreachable API says so", networkError, /No valid response from the API/],
  ])("%s", async (_, handler, message) => {
    setUrl("/experiments");
    setup(handler);

    expect(await screen.findByText("Could not load data")).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
