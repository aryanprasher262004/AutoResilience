/**
 * Contract-typed API payloads (types generated from packages/contracts/openapi.json).
 * Values mirror what the backend returned on the kind cluster; nothing here decides
 * safety or scoring, it only shapes responses for the UI under test.
 */
import type {
  DashboardSummary,
  Experiment,
  ExperimentPage,
  ExperimentSummary,
  Readiness,
  Score,
  ServiceList,
  ValidationResult,
} from "@/lib/api/types";

export const ID = "854cf356-56e1-4ce1-833f-7bcbe3550db8";
const T = "2026-10-06T15:04:37.000000Z";

export function experiment(overrides: Partial<Experiment> = {}): Experiment {
  return {
    id: ID,
    name: "checkout pod-delete",
    description: null,
    target: { namespace: "shop", kind: "Deployment", name: "checkout" },
    fault_type: "pod-delete",
    pod_delete_mode: "GRACEFUL",
    duration_seconds: 60,
    affected_replicas: 1,
    state: "CREATED",
    validation_result: null,
    baseline: null,
    chaos: null,
    observation: null,
    score: null,
    orchestration: null,
    created_at: T,
    updated_at: T,
    ...overrides,
  };
}

const check = (name: string, message: string, status: "PASSED" | "FAILED" | "SKIPPED" = "PASSED") => ({
  name,
  message,
  status,
});

export function validation(passed: boolean): ValidationResult {
  return {
    passed,
    policy: { name: "default", description: "Default policy for all namespaces", min_healthy_replicas: 1 },
    policy_selection: { namespace: "shop", policy: "default", rule: "no namespace-specific policy; default applies" },
    static_checks: [
      check("fault_type_supported", "Fault type 'pod-delete' is supported"),
      passed
        ? check("affected_replicas_within_limit", "Affected replicas 1 <= limit 1")
        : check("affected_replicas_within_limit", "Affected replicas 3 > limit 1", "FAILED"),
    ],
    cluster_checks: passed
      ? [
          check("target_workload_exists", "Deployment shop/checkout exists"),
          check("min_healthy_replicas_after_fault", "2 ready - 1 affected = 1 remaining >= minimum 1"),
        ]
      : [check("target_workload_exists", "Skipped: static policy checks failed; cluster not queried", "SKIPPED")],
  };
}

/** A real v3 score (shop/checkout GRACEFUL run). */
export function score(overrides: Partial<Score> = {}): Score {
  return {
    score: 83.6,
    rating: "Good",
    status: "SCORED",
    version: "v3",
    explanation: "Score 83.6 (Good)",
    inputs: {},
    cap_applied: null,
    components: [
      { name: "recovery_time", status: "SCORED", normalized: 1, weight: 35, effective_weight: 35, contribution: 35, raw: {}, reason: "Recovered in 10s" },
      { name: "client_outage", status: "SCORED", normalized: 0.88, weight: 15, effective_weight: 15, contribution: 13.1, raw: { source: "client" }, reason: "Continuous client outage of 8.346s" },
      { name: "request_failures", status: "SCORED", normalized: 0.53, weight: 30, effective_weight: 30, contribution: 15.9, raw: { source: "client" }, reason: "Client saw 20/826 requests fail" },
      { name: "restarts", status: "SCORED", normalized: 1, weight: 10, effective_weight: 10, contribution: 10, raw: {}, reason: "0 container restart(s)" },
      { name: "litmus_verdict", status: "SCORED", normalized: 1, weight: 10, effective_weight: 10, contribution: 10, raw: {}, reason: "Litmus verdict Pass" },
    ],
    ...overrides,
  };
}

/** Platform UNKNOWN: the backend stores a score record with no number. */
export const notScored = (): Score => ({
  score: null,
  rating: null,
  status: "NOT_SCORED",
  version: "v3",
  explanation: "Not scored: the outcome is UNKNOWN for a platform reason (LITMUS_TIMEOUT), so resilience cannot be judged.",
  inputs: {},
  cap_applied: null,
  components: [],
});

export function summary(overrides: Partial<ExperimentSummary> = {}): ExperimentSummary {
  return {
    id: ID,
    name: "fragile pod-delete graceful",
    target: { namespace: "resilience-sandbox", kind: "Deployment", name: "fragile" },
    fault_type: "pod-delete",
    pod_delete_mode: "GRACEFUL",
    affected_replicas: 1,
    duration_seconds: 30,
    state: "COMPLETED",
    auto: true,
    has_baseline: true,
    score: { score: 83.9, rating: "Good", status: "SCORED", version: "v3" },
    time_to_recovery_seconds: 10,
    client_outage_seconds: 8.346,
    outcome_reason: "1 replacement pod(s) Ready, then 4 consecutive samples >= 1 available",
    created_at: T,
    updated_at: T,
    ...overrides,
  };
}

export const page = (items: ExperimentSummary[], total = items.length, offset = 0, limit = 25): ExperimentPage => ({
  items,
  total,
  limit,
  offset,
});

export function dashboard(namespaces: string[] = ["resilience-sandbox", "shop"]): DashboardSummary {
  return {
    total: 2,
    by_state: {},
    outcomes: { active: 0, completed: 2, failed: 0, aborted: 0, undetermined: 0 },
    scores: { version: "v3", count: 0, average: null, minimum: null, maximum: null, by_rating: {}, not_recovered: 0, not_scored: 0, other_versions: 0 },
    recovery_time_seconds: { count: 0, median: null, minimum: null, maximum: null },
    client_outage_seconds: { count: 0, median: null, minimum: null, maximum: null },
    score_history: [],
    namespaces: namespaces.map((namespace) => ({ namespace, total: 1, completed: 1, last_activity: T })),
    recent: [],
  };
}

export const services = (): ServiceList => ({
  excluded_namespaces: ["kube-node-lease", "kube-public", "kube-system", "litmus", "local-path-storage", "monitoring"],
  items: [
    {
      namespace: "shop",
      kind: "Deployment",
      name: "checkout",
      desired_replicas: 2,
      current_replicas: 2,
      ready_replicas: 2,
      available_replicas: 2,
      health: "HEALTHY",
      created_at: T,
      experiment_count: 0,
      latest_experiment: null,
      latest_score: null,
    },
  ],
});

export const ready = (): Readiness => ({
  status: "ready",
  checks: [{ name: "database", status: "pass", reason: null, detail: "localhost:5432/autoresilience at revision 08697f19aec0" }],
});

export const databaseDown = (): Readiness => ({
  status: "not_ready",
  checks: [
    {
      name: "database",
      status: "fail",
      reason: "database_unreachable",
      detail: "Cannot connect to localhost:5432/autoresilience: connection failed: Connection refused",
    },
  ],
});
