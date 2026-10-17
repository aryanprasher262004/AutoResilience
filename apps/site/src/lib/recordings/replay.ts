/**
 * Replay model for one recorded experiment. Everything here is derived from recorded
 * timestamps and counts; nothing is interpolated or invented. Where the evidence does not
 * contain something (e.g. the exact moment Litmus deleted a pod), the model says so.
 */
import type { RecordedExperiment } from "./types";

export type Source = "Engine" | "Prometheus" | "Litmus" | "Kubernetes" | "Client";

export interface ReplayEvent {
  at: number; // epoch ms
  source: Source;
  title: string;
  detail?: string;
}

export interface Phase {
  id: string;
  label: string;
  start: number;
  end: number;
}

export type PodState = "running" | "targeted" | "deleted" | "starting" | "ready";

export interface PodAt {
  name: string;
  role: "target" | "replacement" | "other";
  state: PodState | "absent";
}

export interface Span {
  start: number;
  end: number;
  label: string;
}

export interface ReplayModel {
  start: number;
  end: number;
  phases: Phase[];
  events: ReplayEvent[];
  lanes: { pods: Span[]; replacements: Span[]; failures: Span[]; outages: Span[]; litmus: Span[] };
  desiredReplicas: number | null;
  /** Pods other than the target and its replacement, when the evidence names them. */
  otherPods: string[] | null;
  podsAt(t: number): PodAt[];
  failedRequestsAt(t: number): number;
  phaseAt(t: number): Phase;
}

const ms = (iso: string) => Date.parse(iso);

// Recorded engine states, in lifecycle order, as replay phases.
const STATE_PHASES: [state: string, id: string, label: string][] = [
  ["CREATED", "validate", "Validate"],
  ["BASELINING", "baseline", "Baseline"],
  ["INJECTING", "inject", "Inject"],
  ["OBSERVING", "observe", "Observe"],
  ["RECOVERING", "recover", "Recover"],
  ["COMPLETED", "score", "Score"],
];

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function buildReplay(recording: RecordedExperiment): ReplayModel {
  const run = recording.experiment;
  const since = run.lifecycle.state_since as Record<string, string | undefined>;
  const start = ms(run.lifecycle.requested_at);
  const end = ms(since.COMPLETED ?? run.litmus.finished_at);

  // Phases: one per recorded state; VALIDATING (if recorded) belongs to Validate.
  const starts = STATE_PHASES.flatMap(([state, id, label]) => {
    const at = state === "CREATED" ? start : since[state];
    return at === undefined ? [] : [{ id, label, start: typeof at === "number" ? at : ms(at) }];
  });
  const phases: Phase[] = starts.map((phase, i) => ({
    ...phase,
    end: i + 1 < starts.length ? starts[i + 1].start : end,
  }));

  const impact = run.impact;
  const client = impact.client;
  const replacements = impact.replacement_pods;
  const targets = run.injection.target_pods;
  const engineCreated = ms(run.injection.created_at);
  const faultObserved = ms(run.recovery.fault_observed_at);
  const checks = run.validation.checks;
  const failureIntervals = client?.failure_intervals ?? [];
  const outageWindows = client?.outage?.outage_windows ?? [];

  const events: ReplayEvent[] = [
    { at: start, source: "Engine", title: "Run requested", detail: `Automatic orchestration, ${run.fault.type} (${run.fault.pod_delete_mode})` },
  ];
  if (since.BASELINING) {
    events.push({
      at: ms(since.BASELINING),
      source: "Engine",
      title: `Safety validation passed (${checks.length}/${checks.length} checks)`,
      detail: `Policy “${run.validation.policy.name}”: at most ${run.validation.policy.max_affected_replicas} affected replica(s), at least ${run.validation.policy.min_healthy_replicas} healthy replica(s) must remain`,
    });
  }
  events.push({
    at: ms(run.baseline.captured_at),
    source: "Prometheus",
    title: `Baseline captured (${run.baseline.window_seconds} s window)`,
    detail: `Availability ${run.baseline.availability.status}, restarts ${run.baseline.restarts.status}, server requests ${run.baseline.requests.status}, client ${run.baseline.client?.status ?? "not recorded"}`,
  });
  events.push({
    at: engineCreated,
    source: "Litmus",
    title: `ChaosEngine created for ${targets.join(", ")}`,
    detail: `${run.fault.pod_delete_mode} pod-delete, ${run.fault.duration_seconds} s, policy “${run.injection.safety_policy}”`,
  });
  for (const pod of replacements) {
    events.push({
      at: ms(pod.created_at),
      source: "Kubernetes",
      title: `Replacement ${pod.pod} created`,
      detail: "The fault is observed from here: the controller replaced the deleted pod",
    });
  }
  events.push({
    at: ms(run.injection.injected_at),
    source: "Engine",
    title: `Deletion of ${targets.join(", ")} confirmed`,
    detail: "Litmus running and the targeted pod gone (the exact deletion moment is not recorded)",
  });
  for (const window of outageWindows) {
    events.push({ at: ms(window.start), source: "Client", title: "Client outage began" });
    if (window.end) {
      events.push({
        at: ms(window.end),
        source: "Client",
        title: `Client outage ended${window.seconds !== null ? ` after ${window.seconds} s` : ""}`,
      });
    }
  }
  for (const interval of failureIntervals) {
    const kinds = Object.entries(interval.by_outcome)
      .map(([outcome, n]) => `${n} ${outcome.replace("_", " ")}`)
      .join(", ");
    events.push({
      at: ms(interval.end),
      source: "Client",
      title: `${plural(interval.failed, "failed request")} in this scrape interval`,
      detail: `${kinds}; counted between scrapes ${secondsBetween(interval.start, interval.end)} s apart`,
    });
  }
  for (const pod of replacements) {
    if (pod.ready_at) events.push({ at: ms(pod.ready_at), source: "Kubernetes", title: `Replacement ${pod.pod} Ready` });
  }
  events.push({
    at: ms(run.recovery.recovered_at),
    source: "Engine",
    title: `Replacements Ready: time to recovery ${run.recovery.time_to_recovery_seconds} s`,
    detail: "Measured from replacement creation to Ready (1 s resolution)",
  });
  run.recovery.stable_streak.forEach((sample, i) => {
    events.push({
      at: ms(sample.at),
      source: "Prometheus",
      title: `Stable availability sample ${i + 1}/${run.recovery.stable_streak.length}`,
      detail: `${sample.available_replicas} available replica(s)`,
    });
  });
  events.push({
    at: ms(run.recovery.confirmed_at),
    source: "Engine",
    title: "Recovery confirmed by the recovery rule",
    detail: run.recovery.error_check?.applicable
      ? `Server error ratio ${run.recovery.error_check.error_ratio} within limit over ${run.recovery.error_check.window_seconds} s`
      : "No server traffic baseline: error check not applicable",
  });
  events.push({
    at: ms(run.litmus.finished_at),
    source: "Litmus",
    title: `Litmus finished: verdict ${run.litmus.verdict}`,
    detail: `Experiment ${run.litmus.experiment_status ?? "status not recorded"}`,
  });
  events.push({
    at: end,
    source: "Engine",
    title: `COMPLETED, scored ${run.score.score} (${run.score.rating}, ${run.score.version})`,
    detail: "The score is computed from the stored evidence in the same step",
  });
  // Stable order: by time, then by the order above (Array.prototype.sort is stable).
  events.sort((a, b) => a.at - b.at);

  const replacementNames = new Set(replacements.map((p) => p.pod));
  const otherPods = run.target_after
    ? run.target_after.ready_pods.filter((p) => !replacementNames.has(p) && !targets.includes(p))
    : null;

  function podsAt(t: number): PodAt[] {
    const pods: PodAt[] = (otherPods ?? []).map((name) => ({ name, role: "other", state: "running" }));
    for (const name of targets) {
      const state: PodState = t < engineCreated ? "running" : t < faultObserved ? "targeted" : "deleted";
      pods.push({ name, role: "target", state });
    }
    for (const pod of replacements) {
      const created = ms(pod.created_at);
      const ready = pod.ready_at ? ms(pod.ready_at) : Infinity;
      pods.push({
        name: pod.pod,
        role: "replacement",
        state: t < created ? "absent" : t < ready ? "starting" : "ready",
      });
    }
    return pods.sort((a, b) => a.name.localeCompare(b.name, "en", { numeric: true }));
  }

  return {
    start,
    end,
    phases,
    events,
    lanes: {
      pods: targets.map((name) => ({ start: engineCreated, end: faultObserved, label: `${name} targeted` })),
      replacements: replacements.map((p) => ({
        start: ms(p.created_at),
        end: p.ready_at ? ms(p.ready_at) : end,
        label: `${p.pod} starting`,
      })),
      failures: failureIntervals.map((i) => ({ start: ms(i.start), end: ms(i.end), label: `${i.failed} failed` })),
      outages: outageWindows.map((w) => ({
        start: ms(w.start),
        end: w.end ? ms(w.end) : end,
        label: w.seconds !== null ? `${w.seconds} s outage` : "outage (end not recorded)",
      })),
      litmus: [{ start: engineCreated, end: ms(run.litmus.finished_at), label: "Litmus run" }],
    },
    desiredReplicas: numberOrNull(run.baseline.availability.values.desired_replicas),
    otherPods,
    podsAt,
    failedRequestsAt: (t) => failureIntervals.filter((i) => ms(i.end) <= t).reduce((sum, i) => sum + i.failed, 0),
    phaseAt: (t) => [...phases].reverse().find((p) => t >= p.start) ?? phases[0],
  };
}

function secondsBetween(a: string, b: string): number {
  return Math.round((ms(b) - ms(a)) / 100) / 10;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

/** "T+12.3 s" relative to `origin`; negative before it. */
export function relative(t: number, origin: number): string {
  const s = (t - origin) / 1000;
  const sign = s < 0 ? "−" : "+";
  return `T${sign}${Math.abs(s).toFixed(1)} s`;
}

export function utc(iso: string | number): string {
  const d = new Date(iso);
  return `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 19)} UTC`;
}
