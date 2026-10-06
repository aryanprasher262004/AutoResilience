# 04 · Component Design

| | |
|---|---|
| **Purpose** | Per-component design: responsibilities, internal workflow, files, classes and functions, external interfaces, failure handling, and extension points. |
| **Source of truth** | Source files named in each section, at `92e33dd`. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [03-system-architecture](03-system-architecture.md) (overview), [05-system-workflows](05-system-workflows.md) (sequences), [appendix/api-overview](appendix/api-overview.md) |

All content is Level C (verified from implementation) unless marked otherwise. Paths are
relative to `apps/api/app/` for the backend and to `apps/web/src/` for the frontend.

---

## 1. Frontend (web console)

| Aspect | Detail |
|---|---|
| **Responsibilities** | Self-service configuration (builder), display of server safety results, start confirmation, live monitoring, abort, history, reports, services inventory, readiness status. |
| **Internal workflow** | Pages → components → TanStack Query hooks (`lib/api/queries.ts`) → `lib/api/client.ts` (`fetch` to `/api/backend/*`) → Next.js rewrite to `AUTORESILIENCE_API_URL` (resolved at build time, `next.config.ts`). |
| **Important files** | `app/**/page.tsx` (routes); `components/experiment/builder/*` (Configure → Safety → Review); `components/experiment/room/*` (live room: `experiment-room.tsx`, `abort-dialog.tsx`, `score-panel.tsx`, `impact-recovery.tsx`, `lifecycle.tsx`, `live-status.tsx`, `metrics-table.tsx`, `events-tab.tsx`, `evidence-tab.tsx`, `outcome-banner.tsx`); `components/history/history-view.tsx`; `components/report/report-view.tsx`; `components/services/*`; `components/shell/api-status.tsx`; `lib/evidence.ts`; `lib/experiment-state.ts` |
| **Important functions/types** | `ApiError` (`unavailable`, `fieldErrors()`); `api.*` client methods; hooks `useExperiment`, `useExperimentHistory`, `useDashboardSummary`, `useServices`, `useService`, `useReadiness`; `STATE_META`, `isTerminal`, `presentState`; evidence readers `readOrchestration`, `readLitmus`, `readRecovery`, `readImpact`, `readTargetEvidence`; builder `checkObvious`, `toPayload`, `serverFieldErrors`, `initialValues`; `createQueryClient` |
| **External interfaces** | The HTTP API only ([appendix/api-overview](appendix/api-overview.md)). Types are generated from `packages/contracts/openapi.json`. |
| **Failure handling** | Network failure or a bare 5xx → `ApiError.unavailable` ("No valid response from the API"); JSON errors show the backend `detail`; 422 `loc` paths are mapped back onto form fields; readiness 503 is treated as an answer (not ready), not as a failure. |
| **Design constraints** | The builder never re-implements safety rules: client-side checks are limited to required fields and positive integers. Free-form evidence is read through runtime-checked readers; missing data is shown as "No data". |
| **Extension points** | New pages via the App Router; new evidence readers in `lib/evidence.ts`; new fault parameters in `lib/experiment-options.ts` (an `Exhaustive` type guard fails the typecheck when backend enums change). |

## 2. Experiment API

| Aspect | Detail |
|---|---|
| **Responsibilities** | Input validation (Pydantic), the experiment lifecycle endpoints, history, dashboard, services, readiness, and error mapping. |
| **Internal workflow** | Route → dependency injection (`get_db`, `get_kubernetes_adapter`, `get_prometheus_client`, `get_chaos_provider`, `get_policy_resolver`, `get_now`, `get_observation_config`, `get_start_wait`) → service function → commit → response model. |
| **Important files** | `api/routes/experiments.py`, `api/routes/reports.py` (history and dashboard), `api/routes/targets.py` (services), `api/routes/ready.py`, `api/routes/health.py`, `api/errors.py`, `schemas/*.py`, `main.py` |
| **Important functions** | `create_experiment`, `validate_experiment`, `capture_experiment_baseline`, `inject_fault`, `observe_experiment`, `run_experiment`, `abort`, `get_experiment_score`, `experiment_history`, `get_dashboard_summary`, `get_services`, `get_service`, `get_readiness`; `_manual_only` (409 for auto runs), `_get_or_404`; `register_error_handlers` |
| **External interfaces** | REST/JSON; OpenAPI at `/openapi.json` and committed in `packages/contracts/openapi.json` |
| **Failure handling** | 422 (schema and constraints), 404 (unknown id), 409 (wrong state, `InvalidTransitionError`, or auto-driven), 503 (database unreachable or unmigrated, via `errors.py`; cluster unreachable for `/services`). Other exceptions → 500. |
| **Concurrency** | `/run` and `/abort` hold a per-experiment in-process lock (`experiment_lock`), shared with the reconciler. This assumes a single API process (`docs/orchestration.md`). |
| **Extension points** | Placeholders (`# OWNER` / `# Intended`): `routes/safety.py` (`GET /api/v1/safety-policy`), `routes/coverage.py` (coverage endpoints), `schemas/safety.py`, `schemas/coverage.py`. Not implemented. |

## 3. Safety (policy, evaluator, validation)

| Aspect | Detail |
|---|---|
| **Responsibilities** | Select a policy by namespace; evaluate static and cluster checks; persist an auditable validation result. |
| **Internal workflow** | `preflight.run_validation`: CREATED → VALIDATING (commit) → `complete_validation`: `evaluate_static` → if all pass, `kubernetes.get_workload_status` → `evaluate_cluster` (or ERROR/SKIPPED checks) → `validation_result` → BASELINING or VALIDATION_FAILED. |
| **Important files** | `domain/safety_policy.py`, `services/safety/policy_evaluator.py`, `services/orchestration/preflight.py` |
| **Important classes/functions** | `SafetyPolicy` (frozen dataclass), `DEFAULT_SAFETY_POLICY`, `SANDBOX_POLICY`, `POLICIES_BY_NAMESPACE`, `SYSTEM_NAMESPACES`, `policy_for_namespace`, `policy_selection`; `CheckStatus`, `CheckResult`, `ValidationResult`, `evaluate_static`, `evaluate_cluster`, `skipped_cluster_checks`, `errored_cluster_checks` |
| **External interfaces** | `POST /experiments/{id}/validate`; called by the reconciler for auto runs |
| **Failure handling** | A cluster error produces ERROR checks (never PASSED). Static failures skip the cluster query. All static checks run without short-circuiting, so every reason is reported. |
| **Extension points** | New policies by adding to `POLICIES_BY_NAMESPACE` (code review is required by design); persisted policies were intended (`db/models/safety_policy.py` placeholder), not implemented. |

Details: [06-safety-framework](06-safety-framework.md).

## 4. Kubernetes adapter

| Aspect | Detail |
|---|---|
| **Responsibilities** | Read-only cluster facts: workload status with pod readiness, live pod names, cluster-wide workload inventory. |
| **Important file** | `integrations/kubernetes_adapter.py` |
| **Classes** | `KubernetesAdapter`, `WorkloadStatus` (desired, running, ready, selector, ready pod names), `WorkloadSummary` (inventory row), `ClusterUnavailableError` |
| **Functions** | `get_workload_status(target)` (reads the Deployment or StatefulSet, then lists pods by its selector); `live_pod_names(ns, names)`; `list_workloads()` (`list_deployment_for_all_namespaces` + `list_stateful_set_for_all_namespaces`); `label_selector_to_string`; `_is_running` (phase Running, not terminating); `_is_ready` (running and condition Ready=True) |
| **External interfaces** | Kubernetes API via the official Python client; kubeconfig context `KUBE_CONTEXT`; request timeout `KUBE_REQUEST_TIMEOUT_SECONDS` (5 s) |
| **Failure handling** | 404 → `None`; any other API, config, network or OS error → `ClusterUnavailableError`; an empty selector is refused (it would match every pod). |
| **Invariant** | Only `read_*`/`list_*` calls (asserted by `assert_read_only` in tests). |

## 5. Prometheus client

| Aspect | Detail |
|---|---|
| **Responsibilities** | Execute PromQL as instant queries; return scalars, instant vectors, or raw range-vector samples. |
| **Important file** | `integrations/prometheus_client.py` |
| **Classes/functions** | `PrometheusClient.query` (instant vector → `Sample`), `query_raw` (matrix → `Series` with raw timestamps), `query_value` (single value or `None`), `PrometheusError` |
| **External interfaces** | HTTP GET `{PROMETHEUS_URL}/api/v1/query` (default `http://localhost:9090`), timeout `PROMETHEUS_TIMEOUT_SECONDS` (5 s) |
| **Failure handling** | Any HTTP, decode or status error → `PrometheusError`; callers decide (baseline group ERROR; observation retries until a deadline, then UNKNOWN `PROMETHEUS_UNAVAILABLE`). |

## 6. Chaos provider (LitmusChaos)

| Aspect | Detail |
|---|---|
| **Responsibilities** | The only cluster writer. Create a pod-delete ChaosEngine from typed fields, read status and ChaosResult, stop, and delete its own objects. |
| **Important file** | `integrations/chaos_provider.py`; cluster prerequisites `chaos/templates/pod-delete.yaml`, `chaos/rbac/pod-delete-rbac.yaml` |
| **Classes/functions** | `LitmusChaosProvider` (`start_pod_delete`, `get_status`, `get_result`, `stop`, `delete_owned`, `_require_chaos_setup`); `PodDeleteRequest`; `FaultStatus`/`FaultPhase` (PENDING, RUNNING, COMPLETED, FAILED); `build_pod_delete_engine`; `parse_engine_status`; `engine_name(id) = "ar-<id>"`; `ChaosProviderError`, `ChaosEngineExistsError` |
| **Engine content** | `appinfo` (namespace, selector, kind); env `TOTAL_CHAOS_DURATION = CHAOS_INTERVAL = duration`, `FORCE`, `TARGET_PODS`, `PODS_AFFECTED_PERC=""`, `SEQUENCE=parallel`; `annotationCheck: false`; `jobCleanUpPolicy: delete`; labels `app.kubernetes.io/managed-by=autoresilience`, `autoresilience.io/experiment-id`, `autoresilience.io/pod-delete-mode`; service account `autoresilience-chaos` |
| **Failure handling** | System namespace → refused; missing ChaosExperiment or ServiceAccount → `ChaosProviderError`; HTTP 409 on create → `ChaosEngineExistsError`; `delete_owned` refuses a wrong name or wrong labels; missing objects count as done. |
| **Extension points** | Other fault types would need new engine builders and support in `SUPPORTED_FAULT_TYPES` (future work). |

## 7. Baseline

| Aspect | Detail |
|---|---|
| **Responsibilities** | Capture steady-state evidence over `BASELINE_WINDOW_SECONDS` (300 s) before injection. |
| **Important file** | `services/orchestration/baseline.py` (contract: `monitoring/prometheus/queries.md`) |
| **Functions** | `baseline_queries`, `capture_baseline`, `run_baseline`; group builders `_availability` (needs ≥ `MIN_SAMPLES` = 4), `_restarts`, `_requests`, `_client`; `pod_name_regex`, `client_selector` |
| **Output** | `{status: CAPTURED|FAILED, captured_at, window_seconds, availability, restarts, requests, client, failure_reasons}`. Each group is `{status: OK|UNAVAILABLE|ERROR, message, values}`. |
| **Failure handling** | Required groups (availability, restarts) not OK, or an optional group in ERROR → FAILED; the experiment stays BASELINING (retryable) until `BASELINE_TIMEOUT_SECONDS` (180 s) under orchestration. |

## 8. Injection

| Aspect | Detail |
|---|---|
| **Responsibilities** | Re-validate, create exactly one engine, confirm the target pods are gone, then enter OBSERVING. |
| **Important file** | `services/orchestration/injection.py` |
| **Functions** | `start_injection` (idempotent; persists engine identity), `advance_injection` (one poll), `run_injection` (blocking loop for the manual endpoint), `_prepare` (guards: passing validation, CAPTURED baseline, same policy name, pod-delete, live cluster re-check; first N ready pods by name), `_poll_deletion`, `_stop_quietly`, `_fail` |
| **Failure handling** | Any guard fails → INJECTION_FAILED with `chaos.failure_reason`. An existing engine at create time (interrupted earlier attempt) is stopped and the run failed (never run twice). Litmus FAILED, unreadable status, or pods still present after `CHAOS_START_TIMEOUT_SECONDS` (120 s) → engine stopped, INJECTION_FAILED. |

## 9. Observation and recovery analyzer

| Aspect | Detail |
|---|---|
| **Responsibilities** | Wait for Litmus to finish; measure impact; decide recovery; decide the final state; trigger scoring in the same transaction. |
| **Important files** | `services/orchestration/observation.py`, `services/orchestration/recovery.py` |
| **Classes/functions** | `ObservationConfig`, `Cause` (platform, application, conflicting_evidence), `_Unknown`; `advance_observation`, `_observe_litmus`, `_evaluate_recovery`, `_measure`, `_check_requests`, `_target_evidence`, `_raise_not_recovered`; `RecoveryRule`, `PodTimes`, `RecoveryFinding`, `observation_queries`, `client_window_counts`, `client_outage`, `find_recovery`, `error_check`, `window_request_queries` |
| **Failure handling** | Every non-success path becomes UNKNOWN with `reason_code` and `cause` ([08](08-recovery-framework.md)). Prometheus errors are retried until the deadline. |

## 10. Scoring engine

| Aspect | Detail |
|---|---|
| **Responsibilities** | Compute an explainable, versioned score from stored evidence only. |
| **Important file** | `services/scoring/resilience_score.py` |
| **Classes/functions** | `CURRENT_VERSION = "v3"`, `SUPPORTED_VERSIONS = (v1, v2, v3)`, `WeightsV1/V2/V3`, `Thresholds`, `OutageThresholds`, `RATING_BANDS`, `Component`, `ScoreStatus`, `ComponentStatus`; component functions `recovery_component`, `availability_component`, `error_ratio_component`, `restarts_component`, `litmus_component`, `request_failures_component`, `_client_failures`, `client_outage_component`; `_components`, `_not_scored`, `score_experiment` |
| **Interfaces** | Called by `advance_observation` at the final state; `GET /experiments/{id}/score?version=` recomputes older versions (not persisted). |
| **Failure handling** | Unscorable situations return `NOT_SCORED` with an explanation, never an exception. |

Details: [09-scoring-methodology](09-scoring-methodology.md).

## 11. Database

| Aspect | Detail |
|---|---|
| **Responsibilities** | System of record for configuration and evidence. |
| **Important files** | `db/models/experiment.py`, `db/session.py` (`engine` with `pool_pre_ping=True`, `SessionLocal`, `get_db`), `db/base.py`, `alembic/` |
| **Design** | Portable types (non-native enums, `sa.Uuid`) so tests run on SQLite. JSON columns are reassigned as new dicts on update, so SQLAlchemy detects the change (comment in `observation.py`). |
| **Failure handling** | Unreachable → 503 `Database unavailable at host:port/db` (no credentials); missing schema → 503 with the migration command; `/ready` reports `database_unreachable`, `schema_missing` or `schema_outdated`. |

## 12. Orchestrator (reconciler)

| Aspect | Detail |
|---|---|
| **Responsibilities** | Drive auto experiments to a terminal state, enforce deadlines, abort, and clean up owned chaos objects. |
| **Important file** | `services/orchestration/orchestrator.py` |
| **Classes/functions** | `Reconciler` (`tick`, `run_forever`, `step`, `_advance`, `_give_up`, `_cleanup`, `_needs_work`); `OrchestratorConfig`; `Dependencies`; `request_auto_run`; `abort_experiment`; `experiment_lock`; `TERMINAL`, `ABORTABLE`, `MAX_EVENTS = 50` |
| **Internal workflow** | Every `ORCHESTRATOR_INTERVAL_SECONDS` (5 s): select experiments where (auto and non-terminal) or (terminal with an engine not yet cleaned) → per experiment under lock → one `step`. |
| **Failure handling** | An exception in a step → rollback, `orchestration.last_error`, retry next tick, other experiments unaffected. `ORCHESTRATION_MAX_SECONDS` (1800 s) → UNKNOWN (or ABORTED if UNKNOWN is not reachable from the current state). |
| **Startup** | A daemon thread started by the FastAPI lifespan when `ORCHESTRATOR_ENABLED=true`. |

## 13. History, dashboard and services analysis

| Aspect | Detail |
|---|---|
| **Responsibilities** | Server-side aggregation for the console: paged and filtered history, dashboard statistics, the service inventory joined with history. |
| **Important files** | `services/analysis/history.py` (`summarize`, `outcome_reason`, `query_history`, `dashboard_summary`), `services/analysis/services.py` (`list_services`, `service_detail`, `health`, `latest_score`, `is_system_namespace`) |
| **Notable rules** | Dashboard score statistics include the **current version only**; other versions and NOT_SCORED are counted separately. Service health: `SCALED_TO_ZERO` (desired 0), `HEALTHY` (ready ≥ desired), `DEGRADED`, `UNAVAILABLE`; plus `NOT_FOUND`/`UNKNOWN` in the detail view. |
| **Docs** | `docs/history-and-reports.md`, `docs/services.md` |

## 14. Report generator

| Aspect | Detail |
|---|---|
| **Current implementation** | **Frontend only**: `components/report/report-view.tsx`, route `/reports/[id]`. Sections: Summary, Configuration, Safety validation, Baseline and measurements, Fault/impact/recovery, Resilience Score. Printable through browser print CSS (`globals.css @media print`). |
| **Not implemented** | Server-side report generation, PDF or other document export, report persistence. The backend `reports.py` serves history and dashboard data only. |
| **Future implementation** | A server-side, versioned report artefact (future work, [21](21-future-work.md)). |

## 15. Readiness and error mapping

| Aspect | Detail |
|---|---|
| **Files** | `services/readiness.py` (`check_database`, `migration_head`, `readiness`), `api/routes/ready.py`, `api/errors.py` |
| **Behaviour** | `/health`: no I/O, `{"status":"ok"}`. `/ready`: `SELECT 1`, then `alembic_version` compared with the script head; 200 `ready` or 503 `not_ready` with a reason. |

## 16. Client load generator (evaluation instrument)

| Aspect | Detail |
|---|---|
| **Responsibilities** | Produce client-side ground truth per target: per-outcome counters, latency histogram, outage duration and timing. |
| **File** | `infra/sample-app/loadgen/loadgen.py` (stdlib Python, mounted from a ConfigMap; Deployment in `infra/sample-app/shop.yaml`) |
| **Behaviour** | One sequential worker per target; one request every `INTERVAL_SECONDS` (0.1 s) on a **new connection** (no keep-alive); `TIMEOUT_SECONDS` = 1. Outcomes: `success` (< 500), `http_error` (≥ 500), `timeout`, `connection_error`. An outage starts at the start of the first failing request after a success and ends at the start of the next successful request; down time accrues continuously. |
| **Metrics** | `loadgen_requests_total{target_namespace,target_workload,outcome}`, `loadgen_request_duration_seconds` (histogram), `loadgen_outage_seconds_total`, `loadgen_outages_total`, `loadgen_last_outage_start_timestamp_seconds`, `loadgen_last_outage_end_timestamp_seconds` |
| **Targets** | `shop/checkout`, `shop/frontend`, `resilience-sandbox/fragile` (env `TARGETS`). `monitoring/prometheus/queries.md` and the v2 doc list only the first two (stale). |

---

## Related documents
[03-system-architecture](03-system-architecture.md) · [05-system-workflows](05-system-workflows.md) · [06-safety-framework](06-safety-framework.md) · [07-evidence-framework](07-evidence-framework.md) · [08-recovery-framework](08-recovery-framework.md) · [09-scoring-methodology](09-scoring-methodology.md) · [appendix/repository-map](appendix/repository-map.md)

## Missing information
- `core/logging.py` is a placeholder: structured logging is not implemented (only `logging.getLogger` in `errors.py` and `orchestrator.py`).
- `frontend_origin` (`core/config.py`) is defined but unused: there is no CORS middleware, because the console reaches the API through a same-origin rewrite.
- No authentication or authorization exists in the API or the console (verified by searching the code).

## Open questions
- Should the report be described as a "report generator" in the paper? Recommended: "printable evidence report view".
