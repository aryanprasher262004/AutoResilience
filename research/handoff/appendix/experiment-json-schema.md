# Appendix · Experiment JSON Schema

| | |
|---|---|
| **Purpose** | (1) The shape of a stored AutoResilience experiment record (`GET /experiments/{id}`), especially the free-form JSON evidence columns, as produced by the code. (2) The schema of the research dataset `research/experiment-results.json` / `.csv`. Extraction scripts for the campaign need both. |
| **Source of truth** | `schemas/experiment.py` (typed parts); `services/orchestration/{preflight,baseline,injection,observation,recovery,orchestrator}.py` and `services/scoring/resilience_score.py` (JSON contents); `research/experiment-results.json`. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [../07-evidence-framework](../07-evidence-framework.md), [../13-experimental-methodology](../13-experimental-methodology.md) §3 |

Notation: `T?` means nullable or optional. Timestamps are ISO-8601 strings with a timezone.
The fields listed are those written by the code; the API models (`ExperimentRead`) type some
of these blocks loosely as `dict`.

---

## 1. Stored experiment record (`ExperimentRead`)

```text
id: uuid
name: str (1–200)
description: str?
state: CREATED | VALIDATING | BASELINING | INJECTING | OBSERVING | RECOVERING |
       COMPLETED | VALIDATION_FAILED | INJECTION_FAILED | ABORTED | UNKNOWN
target: { namespace: str, kind: Deployment | StatefulSet, name: str }
fault_type: pod-delete | pod-cpu-hog | pod-memory-hog | pod-network-latency
pod_delete_mode: GRACEFUL | FORCE
duration_seconds: int > 0
affected_replicas: int > 0
validation_result: ValidationResult?
baseline: Baseline?
chaos: Chaos?
observation: Observation?
score: Score?
orchestration: Orchestration?
created_at, updated_at: datetime
```

### 1.1 `validation_result`

```text
passed: bool
static_checks: [ { name, status: PASSED|FAILED|ERROR|SKIPPED, message } ]
    names: fault_type_supported, namespace_not_forbidden, namespace_allowed,
           duration_within_limit, affected_replicas_within_limit
cluster_checks: [ { name, status, message } ]
    names: target_workload_exists, target_has_running_pods, min_healthy_replicas_after_fault
policy: { name, description, max_duration_seconds, max_affected_replicas,
          min_healthy_replicas, forbidden_namespaces[], allowed_namespaces[]? }
policy_selection: { namespace, policy, rule }
```

### 1.2 `baseline`

```text
status: CAPTURED | FAILED
captured_at: datetime
window_seconds: int
availability: { status: OK|UNAVAILABLE|ERROR, message,
                values: { desired_replicas, available_replicas_avg, available_replicas_min,
                          availability_ratio, samples } }
restarts:     { status, message, values: { restarts_total, restarts_in_window } }
requests:     { status, message, values: { request_rate_rps, error_rate_rps, error_ratio? } }
client:       { status, message, values: { client_rate_rps, client_failure_rate_rps,
                client_failure_ratio?, client_latency_p95_seconds?, client_outage_seconds?,
                client_outages? } }
failure_reasons: [str]
```

### 1.3 `chaos`

```text
provider: "litmus"
experiment: "pod-delete"
pod_delete_mode: GRACEFUL | FORCE
safety_policy: str
engine_name: "ar-<id>"
namespace: str
target_pods: [str]
duration_seconds: int
created_at: datetime            # fault start t_f
injected_at: datetime?          # deletion confirmed → OBSERVING
status: { phase, engine_status, experiment_status, verdict, experiment_pod }?
failure_reason: str?
stopped: bool?   stop_error: str?
```

### 1.4 `observation`

```text
rule: str                                  # RecoveryRule.describe()
evaluations: int
updated_at: datetime
last_error: str?
litmus: { phase, engine_status, experiment_status, verdict, experiment_pod,
          finished_at?, last_error?,
          chaos_result?: { phase, verdict, fail_step?, probe_success_percentage? } | { error } }
impact: {
  window_seconds: int
  availability_samples: int
  min_available_replicas: int?
  availability_dip_observed: bool
  restarts_in_window: int?
  requests_in_window: float?          # server
  errors_in_window: float?            # server 5xx
  client: {
    status: OK | UNAVAILABLE, reason?
    requests, success, http_error, connection_error, timeout, failed: int
    failure_ratio: float?
    counted_from, counted_to: datetime?
    starts_before_fault: bool
    failure_intervals: [ { from, to, failed, by_outcome{} } ]
    latency_p95_seconds: float?
    outage: { status: OK | INSUFFICIENT_DATA,
              pattern: NONE | CONTINUOUS | INTERMITTENT | INSUFFICIENT_DATA,
              reason, outage_seconds, outages, reset_detected, starts_before_fault,
              counted_from, counted_to,
              outage_windows: [ { start, end?, seconds? } ] }
  }
  replacement_pods: [ { pod, created_at, ready_at? } ]
}
recovery: {
  status: RECOVERED | NOT_RECOVERED
  message
  fault_observed_at, recovered_at, confirmed_at: datetime?
  time_to_recovery_seconds: float?
  stable_streak: [ [datetime, value] ]
  max_sample_gap_seconds: float?
  error_check?: { applicable: bool, ok?, message?, error_ratio?, window_seconds? }
}
target?: { deleted_pods[], deleted_pods_still_present[], ready_pods_now[], desired_replicas_now }
         | { deleted_pods[], error }
result: { status: IN_PROGRESS | COMPLETED | UNKNOWN,
          reason_code: RECOVERED | LITMUS_ERROR | LITMUS_TIMEOUT | LITMUS_UNREADABLE |
                       PROMETHEUS_UNAVAILABLE | INSUFFICIENT_DATA | LITMUS_VERDICT_FAIL |
                       RECOVERY_NOT_OBSERVED | null,
          reason?, cause?: platform | application | conflicting_evidence | null }
```

### 1.5 `score`

See [../09-scoring-methodology](../09-scoring-methodology.md) §7. Components:
`{ name, status: SCORED|NOT_APPLICABLE, raw{}, normalized?, weight, reason, effective_weight, contribution }`.

### 1.6 `orchestration`

```text
mode: auto | manual
requested_at: datetime
state_since: { <STATE>: datetime }
events: [ { at, event } ]            # ≤ 50, newest kept
result: { status, reason_code, reason, cause }?   # orchestrator give-up (BASELINE_TIMEOUT, ORCHESTRATION_TIMEOUT)
abort: { reason, at, engine_stopped?, stop_error?, note? }?
cleanup: { done, at?, engine?, result?, waiting?, error?, attempted_at?, note? }?
last_error: str?
last_tick_at: datetime?
```

## 2. Research dataset (`research/experiment-results.json`)

```text
schema: "autoresilience-research-evidence/1"
generated_at, repository_commit, method
evidence_categories: { <category>: description }
    autoresilience_db_record | real_api_run_partial_record | real_disruption_unattributed |
    real_api_run_documented_only | manual_infrastructure_probe | tests_and_fixtures
autoresilience_database: { location, experiment_count: 0, note }
telemetry_retention_warning: str
real_experiments: [ Record ]                     # 22 (6 partial + 16 unattributed)
documented_runs_without_raw_data: [ Record ]     # 6
manual_infrastructure_probes: [ { record_id, evidence_category, namespace, workload, description, observed, source } ]
raw_client_outage_episodes: [ { target, outage_start, outage_end, outage_seconds_from_gauges,
                                outage_seconds_counter_increase, counter_window,
                                client_requests_in_counter_window{} } ]   # 15
raw_litmus_engines: [ { engine, experiment_id, mode_label, engine_created, TOTAL_CHAOS_DURATION,
                        CHAOS_INTERVAL, FORCE, TARGET_PODS, appinfo, engineState, engineStatus,
                        litmus_status, verdict, last_update, chaosServiceAccount } ]  # 6
```

**Record** (null = unknown; never imputed):

```text
record_id                  LIT-<id8> | TEL-<workload>-<HHMMSS> | DOC-…
evidence_category          see above
attribution                how the record was identified
experiment_id              uuid?   (LIT only)
timestamp_utc              engine creation (LIT) or replacement pod creation (TEL)
namespace, workload, kind, fault, pod_delete_mode?, affected_replicas?, duration_seconds?
validation_result          { value: null, note }   (not retained)
baseline_evidence          { stored: null, post_hoc: { window, requests, failed, request_rate_rps,
                                                       failure_ratio, outage_seconds } }
observation_evidence       { documented?, post_hoc_telemetry: {
                               derivation, client_outage{seconds,start,end,pattern,pattern_basis,…},
                               client_failures{failed,requests,connection_error,timeout,http_error,window,window_note},
                               recovery{replacement_pod,replacement_created,replacement_ready,created_to_ready_seconds,source,note},
                               pre_fault_client_baseline_300s, kubernetes_sampled_min_available,
                               kubernetes_samples_in_window }, deleted_target_pod? }
litmus                     { verdict, status, engine_status, finished, env{}, service_account, source }?
final_state                { value: null, note } | str (documented)
score                      { documented: {v1?, v2?, v3?, value?, version?}, source }?
component_scores           { documented, note }?
code_version               { after_commit, before_commit, meaning }
sources[], notes
```

**CSV columns** (`research/experiment-results.csv`): `record_id, evidence_category,
experiment_id, timestamp_utc, namespace, workload, kind, fault, pod_delete_mode,
affected_replicas, duration_seconds, litmus_verdict, final_state,
replacement_created_to_ready_s, client_outage_s, outage_pattern, client_failed,
client_connection_errors, client_timeouts, client_http_errors, k8s_sampled_min_available,
prefault_baseline_outage_s_300s, documented_score_v3, documented_score_v2,
documented_score_v1, documented_score_version_unstated, values_derivation, code_before_commit,
source`. Empty cells mean unknown.

---

## Related documents
[../07-evidence-framework](../07-evidence-framework.md) · [../09-scoring-methodology](../09-scoring-methodology.md) · [../13-experimental-methodology](../13-experimental-methodology.md) · [../14-current-evidence](../14-current-evidence.md)

## Missing information
- The evidence JSON columns have no machine-checked schema in the backend (stored as `dict`). This document is derived from the code that writes them.

## Open questions
- Should the campaign export include a JSON Schema file validated by the analysis scripts? Recommended.
