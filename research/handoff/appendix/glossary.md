# Appendix · Glossary

| | |
|---|---|
| **Purpose** | Definitions of the terms used across this knowledge base and in any paper, so terminology stays consistent. |
| **Source of truth** | Implementation (names as used in the code) and this knowledge base. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | — |

| Term | Definition | Code / location |
|---|---|---|
| **Experiment** (run) | One configured fault execution with its full evidence record | `experiments` table |
| **Target** | The workload under test: namespace, kind (Deployment/StatefulSet), name | `ExperimentTarget` |
| **Fault** | The injected failure; only `pod-delete` is supported | `FaultType`, `SUPPORTED_FAULT_TYPES` |
| **Deletion mode** | GRACEFUL (the pod's grace period, SIGTERM first) or FORCE (`gracePeriodSeconds=0`) | `PodDeleteMode` |
| **Affected replicas** | Number of pods deleted (blast radius); max 1 by policy | `affected_replicas` |
| **Duration** | `TOTAL_CHAOS_DURATION` = `CHAOS_INTERVAL`: one deletion round, then wait | `build_pod_delete_engine` |
| **Safety policy** | A code-defined set of limits selected by namespace: `default` or `sandbox` | `domain/safety_policy.py` |
| **Sandbox** | Namespace `resilience-sandbox` with a policy allowing 0 remaining replicas | `SANDBOX_POLICY` |
| **System namespaces** | Namespaces never targetable or listed: kube-system, kube-public, kube-node-lease, local-path-storage, litmus, monitoring | `SYSTEM_NAMESPACES` |
| **Static check** | Configuration-only check (fault, namespace, duration, replicas) | `evaluate_static` |
| **Cluster check** | Live-state check (workload exists, ready pods, remaining ≥ minimum) | `evaluate_cluster` |
| **Validation** | Static + cluster checks → BASELINING or VALIDATION_FAILED | `preflight.py` |
| **Baseline** | Steady-state evidence over 300 s before injection; CAPTURED or FAILED | `baseline.py` |
| **Metric group status** | OK / UNAVAILABLE (target lacks the metric; not blocking) / ERROR (query failed) | `MetricStatus` |
| **ChaosEngine** | Litmus custom resource that runs the experiment; named `ar-<experiment id>` | `chaos_provider.py` |
| **Fault start (`t_f`)** | ChaosEngine creation time recorded by AutoResilience | `chaos.created_at` |
| **Observation window (`W`)** | Seconds from `t_f` to the evaluation time (+1) | `_measure` |
| **Replacement pod** | Pod of the target created at or after `t_f` | `find_recovery` |
| **Time to recovery (TTR)** | N-th replacement Ready time − earliest creation among those N replacements (1 s resolution) | `RecoveryFinding.time_to_recovery_seconds` |
| **Stable streak** | ≥ 4 consecutive availability samples ≥ desired replicas, gaps ≤ 40 s | `RecoveryRule` |
| **Recovered** | Replacement + stable streak (+ the 5xx check when applicable) | `find_recovery`, `error_check` |
| **Client** | The load generator's per-target sequential HTTP worker (10 req/s, 1 s timeout) | `loadgen.py` |
| **Client failure** | `http_error` (≥ 500), `connection_error` or `timeout` | loadgen outcomes |
| **Client outage** | Time from the first failing request after a success to the start of the next successful request | `loadgen_outage_seconds_total` |
| **Outage pattern** | NONE / CONTINUOUS / INTERMITTENT / INSUFFICIENT_DATA | `client_outage` |
| **Sampled availability** | Available (or ready) replicas from 15 s Prometheus scrapes | `kube_*_replicas_available` |
| **COMPLETED** | Recovered and Litmus verdict Pass | `advance_observation` |
| **UNKNOWN** | Outcome undetermined; carries `reason_code` and `cause` | `_Unknown` |
| **Cause** | `platform` (tooling or data problem), `application` (target did not recover), `conflicting_evidence` (recovered but Litmus failed) | `Cause` |
| **NOT_SCORED** | A score record without a number (platform or conflicting UNKNOWN, or incomplete evidence) | `_not_scored` |
| **SCORED_NOT_RECOVERED** | Application UNKNOWN, scored with recovery 0 and capped at 40 | `score_experiment` |
| **Resilience Score** | 0–100 composite of weighted, normalized components; versioned (v1, v2, v3 current) | `resilience_score.py` |
| **Component** | One score dimension: recovery_time, client_outage, request_failures, restarts, litmus_verdict (v3) | `Component` |
| **NOT_APPLICABLE** | A component without data; excluded, and the remaining weights re-normalized | `ComponentStatus` |
| **Effective weight** | The declared weight re-normalized over applicable components to sum to 100 | `score_experiment` |
| **Rating** | Excellent ≥ 90, Good ≥ 75, Fair ≥ 50, Poor < 50 | `RATING_BANDS` |
| **Orchestrator / reconciler** | Background thread advancing auto experiments one step per 5 s tick | `Reconciler` |
| **Auto run** | Experiment with `orchestration.mode = "auto"` (started with `POST /run`) | `request_auto_run` |
| **Abort** | Operator stop: own engine stopped, state ABORTED | `abort_experiment` |
| **Owned cleanup** | Deleting only `ar-<id>` objects with matching labels | `delete_owned` |
| **Readiness** | DB reachable and at the migration head (`/ready`), vs liveness (`/health`) | `readiness.py` |
| **Evidence levels A–D** | A controlled; B1 retained real-system data; B2 documented only; C implementation and tests; D intent, inference or future work | [../25-research-integrity](../25-research-integrity.md) |
| **Post-hoc telemetry** | Values re-derived from retained Prometheus samples after the fact (B1), not stored by AutoResilience | `research/experiment-results.json` |
| **Orphan engine** | A ChaosEngine whose experiment record no longer exists; never touched by cleanup | [../14-current-evidence](../14-current-evidence.md) |
| **Modelled warm-up** | `initialDelaySeconds: 10` on `fragile`, an artificial start-up delay | `sandbox.yaml` |

---

## Related documents
[../25-research-integrity](../25-research-integrity.md) · [../22-paper-writing-guide](../22-paper-writing-guide.md)

## Missing information
- None.

## Open questions
- Should "Resilience Score" be renamed in the paper to avoid implying validated resilience measurement (e.g. "explainable resilience indicator")?
