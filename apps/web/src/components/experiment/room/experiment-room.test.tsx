import { act, screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import type { Baseline, Chaos, Experiment, ExperimentState, Observation } from "@/lib/api/types";
import { apiError, json, mockApi } from "@/test/api";
import { ID, experiment, notScored, score, validation } from "@/test/fixtures";
import { renderWithApi } from "@/test/render";

import { ExperimentRoom } from "./experiment-room";

const AT = "2026-10-06T15:04:37Z";
const group = (values: Record<string, number | null>) => ({ status: "OK" as const, message: "ok", values });
const BASELINE: Baseline = {
  status: "CAPTURED",
  captured_at: AT,
  window_seconds: 300,
  failure_reasons: [],
  availability: group({ desired_replicas: 2, available_replicas_min: 2 }),
  restarts: group({ restarts: 0 }),
  requests: group({ request_rate: 10.98, error_ratio: 0 }),
};
const CHAOS: Chaos = {
  provider: "litmus",
  experiment: "pod-delete",
  engine_name: `ar-${ID}`,
  namespace: "shop",
  pod_delete_mode: "GRACEFUL",
  target_pods: ["checkout-7d44884fd9-knl78"],
  injected_at: AT,
};
const observation = (status: string, extra: Partial<Observation["result"]> = {}): Observation => ({
  evaluations: 6,
  rule: "recovered when >= affected_replicas replacement pods are Ready, then >= 4 consecutive samples",
  updated_at: AT,
  litmus: { verdict: status === "UNKNOWN" ? "Awaited" : "Pass" },
  result: { status, ...extra },
});

/** The evidence a real auto run has accumulated when it reaches `state`. */
function runAt(state: ExperimentState, overrides: Partial<Experiment> = {}): Experiment {
  const order: ExperimentState[] = ["VALIDATING", "BASELINING", "INJECTING", "OBSERVING", "RECOVERING", "COMPLETED"];
  const reached = (s: ExperimentState) => order.indexOf(state) >= order.indexOf(s) || ["UNKNOWN"].includes(state);
  return experiment({
    state,
    orchestration: { mode: "auto", requested_at: AT, state_since: { [state]: AT }, events: [] },
    validation_result: reached("BASELINING") ? validation(true) : null,
    baseline: reached("INJECTING") ? BASELINE : null,
    chaos: reached("OBSERVING") ? CHAOS : null,
    observation: reached("RECOVERING") ? observation(state === "RECOVERING" ? "RECOVERING" : "COMPLETED") : null,
    score: state === "COMPLETED" ? score() : null,
    ...overrides,
  });
}

const UNKNOWN = runAt("UNKNOWN", {
  observation: observation("UNKNOWN", { reason_code: "LITMUS_TIMEOUT", cause: "platform", reason: "Litmus did not finish within the grace period" }),
  score: notScored(),
});
const ABORTED = runAt("OBSERVING", {
  state: "ABORTED",
  orchestration: {
    mode: "auto",
    requested_at: AT,
    abort: { reason: "Aborted from the web console", at: AT, engine_stopped: `ar-${ID}` },
  },
});

function show(e: Experiment) {
  const api = mockApi().on("GET", `/experiments/${ID}`, e);
  return { api, ...renderWithApi(<ExperimentRoom id={ID} />) };
}

const abortButton = () => screen.queryByRole("button", { name: "Abort experiment" });
const header = () => screen.getByRole("heading", { level: 1 }).parentElement!.parentElement!;

describe("Live experiment room", () => {
  test.each([
    ["VALIDATING", "Validating"],
    ["BASELINING", "Baselining"],
    ["INJECTING", "Injecting"],
    ["OBSERVING", "Observing"],
    ["RECOVERING", "Recovering"],
  ] as const)("active %s: live, abortable, no score yet", async (state, label) => {
    show(runAt(state));

    expect(await screen.findByText("checkout pod-delete")).toBeInTheDocument();
    expect(within(header()).getByText(label)).toBeInTheDocument();
    expect(screen.getByText(/Live · polling every 3 s/)).toBeInTheDocument();
    expect(abortButton()).toBeInTheDocument();
    expect(screen.getByText("Scored automatically when the experiment finishes.")).toBeInTheDocument();
  });

  test("COMPLETED: final, not abortable, shows the stored score and its breakdown", async () => {
    show(runAt("COMPLETED"));

    expect(await screen.findByText("Final state · polling stopped")).toBeInTheDocument();
    expect(within(header()).getByText("Completed")).toBeInTheDocument();
    expect(abortButton()).not.toBeInTheDocument();
    expect(screen.getByText("83.6")).toBeInTheDocument();
    expect(screen.getByText("Methodology v3 · computed from this run's recorded evidence")).toBeInTheDocument();
    expect(screen.getByText("Continuous client outage of 8.346s")).toBeInTheDocument();
  });

  test("UNKNOWN with NOT_SCORED: says 'Not scored' with the backend's reason, shows no number", async () => {
    show(UNKNOWN);

    expect(await screen.findByText("Final state · polling stopped")).toBeInTheDocument();
    expect(within(header()).getByText("Undetermined")).toBeInTheDocument();
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.getByText(notScored().explanation)).toBeInTheDocument();
    expect(screen.queryByText("/ 100")).not.toBeInTheDocument();
    expect(abortButton()).not.toBeInTheDocument();
  });

  test("ABORTED: final, not abortable, explains why there is no score", async () => {
    show(ABORTED);

    expect(await screen.findByText("Final state · polling stopped")).toBeInTheDocument();
    expect(within(header()).getByText("Aborted")).toBeInTheDocument();
    expect(abortButton()).not.toBeInTheDocument();
    expect(
      screen.getByText("Aborted runs are not scored: the experiment was stopped before an outcome was measured."),
    ).toBeInTheDocument();
  });

  test("polls every 3 s while active and stops once the run is terminal", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = mockApi().sequence(
      "GET",
      `/experiments/${ID}`,
      () => json(runAt("OBSERVING")),
      () => json(runAt("RECOVERING")),
      () => json(runAt("COMPLETED")),
    );
    renderWithApi(<ExperimentRoom id={ID} />);
    await screen.findByRole("heading", { level: 1 });
    expect(within(header()).getByText("Observing")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(3_000));
    expect(await within(header()).findByText("Recovering")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(3_000));
    expect(await within(header()).findByText("Completed")).toBeInTheDocument();
    expect(api.requests("GET", `/experiments/${ID}`)).toHaveLength(3);

    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(api.requests("GET", `/experiments/${ID}`)).toHaveLength(3);
    expect(screen.getByText("Final state · polling stopped")).toBeInTheDocument();
  });

  test("a terminal run is fetched once and never polled", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { api } = show(runAt("COMPLETED"));
    await screen.findByText("Final state · polling stopped");

    await act(() => vi.advanceTimersByTimeAsync(30_000));

    expect(api.requests("GET", `/experiments/${ID}`)).toHaveLength(1);
  });

  test("abort sends the reason and shows the run as Aborted", async () => {
    // Like the backend, the abort is persisted: later reads return the aborted run.
    let stored = runAt("OBSERVING");
    const api = mockApi()
      .on("GET", `/experiments/${ID}`, () => json(stored))
      .on("POST", `/experiments/${ID}/abort`, () => json((stored = ABORTED)));
    const { user } = renderWithApi(<ExperimentRoom id={ID} />);

    await user.click(await screen.findByRole("button", { name: "Abort experiment" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(new RegExp(`Only this experiment's ChaosEngine \\(ar-${ID}\\) is stopped`))).toBeInTheDocument();
    await user.clear(within(dialog).getByRole("textbox"));
    await user.type(within(dialog).getByRole("textbox"), "Checkout errors too high");
    await user.click(within(dialog).getByRole("button", { name: "Abort experiment" }));

    expect(await within(header()).findByText("Aborted")).toBeInTheDocument();
    expect(api.requests("POST", `/experiments/${ID}/abort`)[0].body).toEqual({ reason: "Checkout errors too high" });
    expect(abortButton()).not.toBeInTheDocument();
  });

  test("an abort the backend refuses is shown, and the run is re-read", async () => {
    const { api, user } = show(runAt("RECOVERING"));
    api.on("POST", `/experiments/${ID}/abort`, () => apiError(409, "Experiment is COMPLETED; only active experiments can be aborted"));

    await user.click(await screen.findByRole("button", { name: "Abort experiment" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Abort experiment" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The experiment was not aborted");
    expect(alert).toHaveTextContent("409: Experiment is COMPLETED; only active experiments can be aborted");
    expect(api.requests("GET", `/experiments/${ID}`).length).toBeGreaterThanOrEqual(2);
  });

  test("an unknown id says so instead of showing an error", async () => {
    mockApi().on("GET", `/experiments/${ID}`, () => apiError(404, "Experiment not found"));
    renderWithApi(<ExperimentRoom id={ID} />);

    expect(await screen.findByText("Experiment not found")).toBeInTheDocument();
  });
});
