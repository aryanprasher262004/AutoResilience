import { describe, expect, it } from "vitest";

import { copy, fragile } from "@/test/recordings";

import { buildReplay, relative } from "./replay";

describe("buildReplay (recorded fragile run)", () => {
  const data = fragile();
  const model = buildReplay(data);
  const at = (iso: string) => Date.parse(iso);
  const run = data.experiment;

  it("spans the recorded run and orders events by recorded time", () => {
    expect(model.start).toBe(at(run.lifecycle.requested_at));
    expect(model.end).toBe(at(run.lifecycle.state_since.COMPLETED!));
    const times = model.events.map((e) => e.at);
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(model.events[0].title).toBe("Run requested");
    expect(model.events.at(-1)?.title).toBe(`COMPLETED, scored ${run.score.score} (${run.score.rating}, v3)`);
  });

  it("uses only recorded states as phases", () => {
    expect(model.phases.map((p) => p.label)).toEqual(["Validate", "Baseline", "Inject", "Observe", "Score"]);
    expect(model.phaseAt(at(run.injection.injected_at)).label).toBe("Observe");
  });

  it("derives pod states from recorded timestamps only", () => {
    const [target] = run.injection.target_pods;
    const [replacement] = run.impact.replacement_pods;
    const state = (t: number, name: string) => model.podsAt(t).find((p) => p.name === name)?.state;
    expect(state(model.start, target)).toBe("running");
    expect(state(at(run.injection.created_at), target)).toBe("targeted");
    expect(state(at(run.recovery.fault_observed_at), target)).toBe("deleted");
    expect(state(at(replacement.created_at) - 1, replacement.pod)).toBe("absent");
    expect(state(at(replacement.created_at), replacement.pod)).toBe("starting");
    expect(state(at(replacement.ready_at!), replacement.pod)).toBe("ready");
  });

  it("counts client failures only once their scrape interval has ended", () => {
    const [interval] = run.impact.client!.failure_intervals;
    expect(model.failedRequestsAt(at(interval.end) - 1)).toBe(0);
    expect(model.failedRequestsAt(at(interval.end))).toBe(interval.failed);
    expect(model.failedRequestsAt(model.end)).toBe(run.impact.client!.failed);
  });

  it("copes with missing client evidence and unnamed replicas", () => {
    const partial = copy(data);
    partial.experiment.impact.client = null;
    partial.experiment.target_after = null;
    const sparse = buildReplay(partial);
    expect(sparse.lanes.failures).toEqual([]);
    expect(sparse.lanes.outages).toEqual([]);
    expect(sparse.otherPods).toBeNull();
    expect(sparse.failedRequestsAt(sparse.end)).toBe(0);
    expect(sparse.events.some((e) => e.source === "Client")).toBe(false);
  });

  it("formats relative time", () => {
    expect(relative(1500, 0)).toBe("T+1.5 s");
    expect(relative(0, 2000)).toBe("T−2.0 s");
  });
});
