/**
 * Readers for the evidence blocks the API returns as free-form JSON
 * (observation.litmus/recovery/impact/target, orchestration). Each reader checks
 * types at runtime and returns null for anything missing, so the UI can say
 * "No data" instead of guessing. Field names mirror the backend
 * (apps/api/app/services/orchestration/{observation,recovery,orchestrator}.py).
 */
import type { Experiment, ExperimentState } from "./api/types";

type Json = Record<string, unknown>;

const obj = (v: unknown): Json | null =>
  v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Json) : null;
const str = (v: unknown): string | null => (typeof v === "string" && v ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const bool = (v: unknown): boolean | null => (typeof v === "boolean" ? v : null);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

// --- orchestration -----------------------------------------------------------

export type OrchestrationEvent = { at: string; text: string };
export type OrchestrationView = {
  mode: "auto" | "manual";
  requestedAt: string | null;
  stateSince: Partial<Record<ExperimentState, string>>;
  events: OrchestrationEvent[];
  result: { status: string | null; reasonCode: string | null; reason: string | null; cause: string | null } | null;
  abort: {
    reason: string | null;
    at: string | null;
    engineStopped: string | null;
    stopError: string | null;
    note: string | null;
  } | null;
  cleanup: {
    done: boolean | null;
    at: string | null;
    engine: string | null;
    result: string | null;
    waiting: string | null;
    error: string | null;
  } | null;
  lastError: string | null;
  lastTickAt: string | null;
};

export function readOrchestration(e: Experiment): OrchestrationView {
  const o = obj(e.orchestration) ?? {};
  const since = obj(o.state_since) ?? {};
  const result = obj(o.result);
  const abort = obj(o.abort);
  const cleanup = obj(o.cleanup);
  return {
    mode: o.mode === "auto" ? "auto" : "manual",
    requestedAt: str(o.requested_at),
    stateSince: Object.fromEntries(
      Object.entries(since).filter(([, at]) => typeof at === "string"),
    ) as Partial<Record<ExperimentState, string>>,
    events: list(o.events)
      .map(obj)
      .filter((ev): ev is Json => ev !== null && !!str(ev.at) && !!str(ev.event))
      .map((ev) => ({ at: ev.at as string, text: ev.event as string })),
    result: result
      ? {
          status: str(result.status),
          reasonCode: str(result.reason_code),
          reason: str(result.reason),
          cause: str(result.cause),
        }
      : null,
    abort: abort
      ? {
          reason: str(abort.reason),
          at: str(abort.at),
          engineStopped: str(abort.engine_stopped),
          stopError: str(abort.stop_error),
          note: str(abort.note),
        }
      : null,
    cleanup: cleanup
      ? {
          done: bool(cleanup.done),
          at: str(cleanup.at),
          engine: str(cleanup.engine),
          result: str(cleanup.result),
          waiting: str(cleanup.waiting),
          error: str(cleanup.error),
        }
      : null,
    lastError: str(o.last_error),
    lastTickAt: str(o.last_tick_at),
  };
}

// --- Litmus ------------------------------------------------------------------

export type LitmusView = {
  verdict: string | null;
  engineStatus: string | null;
  experimentStatus: string | null;
  finishedAt: string | null;
  failStep: string | null;
  probeSuccess: string | null;
  resultError: string | null;
  stopped: boolean | null;
  lastError: string | null;
};

export function readLitmus(e: Experiment): LitmusView | null {
  const l = obj(e.observation?.litmus);
  if (!l) return null;
  const result = obj(l.chaos_result) ?? {};
  return {
    verdict: str(l.verdict),
    engineStatus: str(l.engine_status),
    experimentStatus: str(l.experiment_status),
    finishedAt: str(l.finished_at),
    failStep: str(result.fail_step),
    probeSuccess: str(result.probe_success_percentage),
    resultError: str(result.error),
    stopped: bool(l.stopped),
    lastError: str(l.last_error),
  };
}

// --- recovery ----------------------------------------------------------------

export type RecoveryView = {
  status: string | null;
  message: string | null;
  faultObservedAt: string | null;
  recoveredAt: string | null;
  confirmedAt: string | null;
  timeToRecoverySeconds: number | null;
  stableSamples: number;
  maxSampleGapSeconds: number | null;
  errorCheck: { applicable: boolean; ok: boolean | null; message: string | null } | null;
};

export function readRecovery(e: Experiment): RecoveryView | null {
  const r = obj(e.observation?.recovery);
  if (!r) return null;
  const check = obj(r.error_check);
  return {
    status: str(r.status),
    message: str(r.message),
    faultObservedAt: str(r.fault_observed_at),
    recoveredAt: str(r.recovered_at),
    confirmedAt: str(r.confirmed_at),
    timeToRecoverySeconds: num(r.time_to_recovery_seconds),
    stableSamples: list(r.stable_streak).length,
    maxSampleGapSeconds: num(r.max_sample_gap_seconds),
    errorCheck: check
      ? { applicable: check.applicable === true, ok: bool(check.ok), message: str(check.message) }
      : null,
  };
}

// --- impact (client + Kubernetes + server) ----------------------------------------

export type OutageWindow = { start: string; end: string | null; seconds: number | null };
export type ClientOutageView = {
  status: string | null;
  pattern: string | null;
  reason: string | null;
  seconds: number | null;
  outages: number | null;
  windows: OutageWindow[];
  resetDetected: boolean | null;
};
export type FailureInterval = { from: string; to: string; failed: number; byOutcome: Record<string, number> };
export type ClientImpactView = {
  status: string | null;
  reason: string | null;
  requests: number | null;
  success: number | null;
  failed: number | null;
  connectionErrors: number | null;
  timeouts: number | null;
  httpErrors: number | null;
  failureRatio: number | null;
  latencyP95Seconds: number | null;
  countedFrom: string | null;
  countedTo: string | null;
  failureIntervals: FailureInterval[];
  outage: ClientOutageView | null;
};
export type ReplacementPod = { pod: string; createdAt: string | null; readyAt: string | null };
export type ImpactView = {
  windowSeconds: number | null;
  availabilitySamples: number | null;
  minAvailable: number | null;
  dipObserved: boolean | null;
  restarts: number | null;
  serverRequests: number | null;
  serverErrors: number | null;
  client: ClientImpactView | null;
  replacementPods: ReplacementPod[];
};

function readClient(v: unknown): ClientImpactView | null {
  const c = obj(v);
  if (!c) return null;
  const o = obj(c.outage);
  return {
    status: str(c.status),
    reason: str(c.reason),
    requests: num(c.requests),
    success: num(c.success),
    failed: num(c.failed),
    connectionErrors: num(c.connection_error),
    timeouts: num(c.timeout),
    httpErrors: num(c.http_error),
    failureRatio: num(c.failure_ratio),
    latencyP95Seconds: num(c.latency_p95_seconds),
    countedFrom: str(c.counted_from),
    countedTo: str(c.counted_to),
    failureIntervals: list(c.failure_intervals)
      .map(obj)
      .filter((i): i is Json => i !== null && !!str(i.from) && !!str(i.to))
      .map((i) => ({
        from: i.from as string,
        to: i.to as string,
        failed: num(i.failed) ?? 0,
        byOutcome: Object.fromEntries(
          Object.entries(obj(i.by_outcome) ?? {}).filter(([, n]) => typeof n === "number"),
        ) as Record<string, number>,
      })),
    outage: o
      ? {
          status: str(o.status),
          pattern: str(o.pattern),
          reason: str(o.reason),
          seconds: num(o.outage_seconds),
          outages: num(o.outages),
          windows: list(o.outage_windows)
            .map(obj)
            .filter((w): w is Json => w !== null && !!str(w.start))
            .map((w) => ({ start: w.start as string, end: str(w.end), seconds: num(w.seconds) })),
          resetDetected: bool(o.reset_detected),
        }
      : null,
  };
}

export function readImpact(e: Experiment): ImpactView | null {
  const i = obj(e.observation?.impact);
  if (!i) return null;
  return {
    windowSeconds: num(i.window_seconds),
    availabilitySamples: num(i.availability_samples),
    minAvailable: num(i.min_available_replicas),
    dipObserved: bool(i.availability_dip_observed),
    restarts: num(i.restarts_in_window),
    serverRequests: num(i.requests_in_window),
    serverErrors: num(i.errors_in_window),
    client: readClient(i.client),
    replacementPods: list(i.replacement_pods)
      .map(obj)
      .filter((p): p is Json => p !== null && !!str(p.pod))
      .map((p) => ({ pod: p.pod as string, createdAt: str(p.created_at), readyAt: str(p.ready_at) })),
  };
}

export type TargetEvidence = {
  deletedPods: string[];
  stillPresent: string[] | null;
  readyNow: string[] | null;
  error: string | null;
};

export function readTargetEvidence(e: Experiment): TargetEvidence | null {
  const t = obj(e.observation?.target);
  if (!t) return null;
  const strings = (v: unknown) => list(v).filter((x): x is string => typeof x === "string");
  return {
    deletedPods: strings(t.deleted_pods),
    stillPresent: Array.isArray(t.deleted_pods_still_present) ? strings(t.deleted_pods_still_present) : null,
    readyNow: Array.isArray(t.ready_pods_now) ? strings(t.ready_pods_now) : null,
    error: str(t.error),
  };
}

// --- baseline group values --------------------------------------------------------

/** A numeric value from a baseline metric group, or null. */
export function groupValue(
  group: { values?: Record<string, unknown> } | null | undefined,
  key: string,
): number | null {
  return num(group?.values?.[key]);
}

export const policyName = (e: Experiment): string | null =>
  str(obj(e.validation_result?.policy)?.name);
