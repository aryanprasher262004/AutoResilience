# 05 · System Workflows

| | |
|---|---|
| **Purpose** | Complete, step-level workflows with sequence diagrams: creation, validation, baseline, injection, observation, recovery, scoring, reporting, abort, cleanup, restart recovery, history, and manual mode. |
| **Source of truth** | `api/routes/experiments.py`, `services/orchestration/*.py`, `apps/web/src/components/**` at `92e33dd`. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [03-system-architecture](03-system-architecture.md), [04-component-design](04-component-design.md), [08-recovery-framework](08-recovery-framework.md) |

All workflows are Level C. Timeouts are configuration defaults from `core/config.py`.

---

## 1. Experiment creation (console: Configure)

```mermaid
sequenceDiagram
    actor U as User
    participant B as Builder (configure-step)
    participant API as POST /experiments
    participant DB as PostgreSQL
    U->>B: name, target (picker from GET /services or manual), fault, mode, duration, replicas
    B->>B: checkObvious(): required fields, positive integers only
    B->>API: ExperimentCreate JSON
    API->>API: Pydantic: DNS label/subdomain patterns, duration > 0, replicas > 0, mode ∈ {GRACEFUL, FORCE}
    alt invalid
        API-->>B: 422 with loc paths
        B-->>U: errors mapped onto fields (serverFieldErrors)
    else valid
        API->>DB: INSERT state=CREATED
        API-->>B: 201 ExperimentRead
    end
```

The builder remembers the payload it created from. Changing the configuration after a
check creates a new experiment on the next check; the earlier one stays in history.

## 2. Validation (console: Safety check)

```mermaid
sequenceDiagram
    participant C as Caller (console or reconciler)
    participant API as POST /validate
    participant PF as preflight
    participant PE as policy_evaluator
    participant K as KubernetesAdapter
    participant DB as PostgreSQL
    C->>API: validate
    API->>PF: run_validation (CREATED → VALIDATING, commit)
    PF->>PE: evaluate_static(spec, policy_for_namespace(ns))
    alt any static check FAILED
        PE-->>PF: cluster checks SKIPPED
    else
        PF->>K: get_workload_status(target)
        alt ClusterUnavailableError
            K-->>PF: cluster checks ERROR
        else
            PF->>PE: evaluate_cluster(spec, policy, status)
        end
    end
    PF->>DB: validation_result {passed, static_checks, cluster_checks, policy, policy_selection}
    PF->>DB: BASELINING if all PASSED else VALIDATION_FAILED
    API-->>C: 200 ExperimentRead (409 if wrong state or auto-driven)
```

The console shows exactly what the server returned. A blocked experiment stays in history
as VALIDATION_FAILED.

## 3. Start (console: Review & start)

```mermaid
sequenceDiagram
    actor U as User
    participant R as Review step
    participant API as POST /run
    participant O as request_auto_run
    participant DB as PostgreSQL
    U->>R: tick "I understand this will delete N pod(s)…"
    U->>R: Start experiment
    R->>API: run (under experiment_lock)
    API->>O: accept CREATED, or BASELINING with passed validation and no baseline
    O->>DB: orchestration = {mode: auto, requested_at, state_since, events, result: null, abort: null, cleanup: null}
    API-->>R: 202 ExperimentRead (409 otherwise)
    R-->>U: navigate to /experiments/{id}
```

## 4. Baseline

```mermaid
sequenceDiagram
    participant R as Reconciler
    participant B as baseline.run_baseline
    participant P as Prometheus
    participant DB as PostgreSQL
    R->>B: state BASELINING
    B->>P: instant queries at one timestamp over W = 300 s
    Note over B,P: availability (desired, avg, min, count ≥ 4)<br/>restarts (total, in window)<br/>requests (series?, rate, 5xx rate)<br/>client (series?, rate, failure rate, p95, outage s, outages)
    B->>DB: baseline JSON (CAPTURED or FAILED)
    alt CAPTURED
        B->>DB: INJECTING
    else FAILED
        Note over R: retried each tick, after 180 s → UNKNOWN BASELINE_TIMEOUT (platform)
    end
```

## 5. Injection

```mermaid
sequenceDiagram
    participant R as Reconciler
    participant I as injection
    participant K as KubernetesAdapter
    participant L as LitmusChaosProvider
    participant DB as PostgreSQL
    R->>I: start_injection (no engine recorded yet)
    I->>I: _prepare: validation passed? baseline CAPTURED? same policy? pod-delete?
    I->>K: get_workload_status → evaluate_cluster again
    I->>I: target_pods = first N ready pods by name
    I->>L: start_pod_delete (requires ChaosExperiment + ServiceAccount in the namespace)
    L-->>I: ar-<id> (409 → stop the existing engine, INJECTION_FAILED)
    I->>DB: chaos {engine_name, target_pods, safety_policy, pod_delete_mode, created_at, ...}
    loop each tick
        R->>I: advance_injection
        I->>L: get_status
        I->>K: live_pod_names(target_pods)
        alt Litmus RUNNING/COMPLETED and pods gone or terminating
            I->>DB: injected_at, OBSERVING
        else Litmus FAILED, or > 120 s since creation
            I->>L: stop (engineState: stop)
            I->>DB: INJECTION_FAILED + failure_reason
        end
    end
```

## 6. Observation (Litmus phase)

```mermaid
sequenceDiagram
    participant R as Reconciler
    participant O as advance_observation
    participant L as Litmus
    participant DB as PostgreSQL
    R->>O: state OBSERVING
    O->>L: get_status(engine)
    alt engine stopped or verdict Error/Stopped
        O->>DB: UNKNOWN LITMUS_ERROR (platform)
    else experiment Completed with verdict Pass/Fail
        O->>L: get_result (ChaosResult: phase, verdict, failStep, probeSuccessPercentage)
        O->>DB: litmus.finished_at, RECOVERING
    else not finished and now > created_at + duration + 180 s
        O->>L: stop
        O->>DB: UNKNOWN LITMUS_TIMEOUT (platform)
    else status unreadable past the deadline
        O->>DB: UNKNOWN LITMUS_UNREADABLE (platform)
    end
```

## 7. Recovery evaluation

```mermaid
sequenceDiagram
    participant R as Reconciler
    participant O as _evaluate_recovery
    participant P as Prometheus
    participant RC as recovery.find_recovery (pure)
    participant DB as PostgreSQL
    R->>O: state RECOVERING
    O->>P: raw availability [W], kube_pod_created, kube_pod_status_ready_time, restarts, server requests and 5xx, client raw counters [W+60 s], client outage raw [W+60 s], p95
    O->>RC: pods, availability, fault_start (engine created_at), desired (baseline), affected
    RC-->>O: RecoveryFinding (replacements Ready? 4 stable samples? gaps?)
    opt recovered and baseline had server traffic
        O->>P: requests and 5xx over the stable window → error_check (≤ baseline + 0.01)
    end
    alt recovered and Litmus Pass
        O->>DB: COMPLETED (reason_code RECOVERED)
    else recovered but Litmus not Pass
        O->>DB: UNKNOWN LITMUS_VERDICT_FAIL (conflicting_evidence)
    else not recovered, 300 s after Litmus finished
        O->>DB: UNKNOWN INSUFFICIENT_DATA (platform) or RECOVERY_NOT_OBSERVED (application)
    else not yet
        O->>DB: observation updated, retry next tick
    end
```

## 8. Scoring

```mermaid
sequenceDiagram
    participant O as advance_observation
    participant S as score_experiment (pure)
    participant DB as PostgreSQL
    O->>S: state, baseline, observation, chaos (only at COMPLETED or UNKNOWN)
    alt UNKNOWN with cause ≠ application, or incomplete evidence
        S-->>O: NOT_SCORED (score null) + explanation
    else
        S-->>O: components, effective weights, score, rating, cap, explanation, inputs
    end
    O->>DB: score JSON in the same transaction as the final state
```

## 9. Reporting (console)

```mermaid
sequenceDiagram
    actor U as User
    participant RV as /reports/[id] (report-view.tsx)
    participant API as GET /experiments/{id}
    U->>RV: open report (from /reports list or the room)
    RV->>API: fetch experiment (polls while non-terminal → "Provisional report")
    RV-->>U: Summary, Configuration, Safety validation, Baseline and measurements,<br/>Fault/impact/recovery, Resilience Score
    U->>RV: Print / save as PDF (browser print, white print theme)
```

No server-side report artefact is produced ([04](04-component-design.md) §14).

## 10. Abort

```mermaid
sequenceDiagram
    actor U as User
    participant D as Abort dialog
    participant API as POST /abort {reason 1–500}
    participant A as abort_experiment
    participant L as Litmus
    participant DB as PostgreSQL
    U->>D: reason, confirm
    D->>API: abort (under experiment_lock)
    API->>A: state ∈ ABORTABLE (CREATED…RECOVERING)?
    alt engine recorded
        A->>L: stop own engine (engineState: stop)
    end
    A->>DB: orchestration.abort {reason, at, engine_stopped | stop_error | note}, ABORTED
    API-->>D: 200 (409 "nothing to abort" if terminal, including UNKNOWN)
```

Pods that were already deleted are not restored; Kubernetes replaces them as usual (shown in
the dialog text).

## 11. Cleanup

```mermaid
sequenceDiagram
    participant R as Reconciler
    participant L as LitmusChaosProvider
    participant DB as PostgreSQL
    R->>DB: terminal experiments with chaos.engine_name and not cleanup.done
    R->>L: get_status
    alt engine still running and finished < 120 s ago
        R->>DB: cleanup.waiting
    else
        R->>L: delete_owned(ns, ar-id, id)
        Note over L: refuse system namespaces and names ≠ ar-id<br/>re-read the engine: labels managed-by + experiment-id must match<br/>delete the engine and ar-id-pod-delete (absent = done)
        R->>DB: cleanup {done, at, engine, result} or {error} (retried)
    end
```

ChaosEngines unknown to the database are never touched. This is why six engines from deleted
development databases remain in `resilience-sandbox` ([14](14-current-evidence.md)).

## 12. Restart recovery

```mermaid
sequenceDiagram
    participant API as API process (restarted)
    participant R as Reconciler
    participant DB as PostgreSQL
    participant L as Litmus
    API->>R: lifespan starts the reconciler thread
    R->>DB: auto experiments not terminal
    alt VALIDATING
        R->>R: complete_validation (resume)
    else INJECTING with an engine recorded
        R->>L: poll the existing engine (never create a second one)
    else OBSERVING / RECOVERING
        R->>R: continue from persisted deadlines (chaos.created_at, litmus.finished_at)
    end
```

Documented verification (B2, `docs/orchestration.md`): an API killed in OBSERVING and
restarted 26 s later resumed to COMPLETED with a single engine.

## 13. History and services

| Workflow | Endpoint | Behaviour |
|---|---|---|
| History list | `GET /experiments/history?q&state&fault_type&namespace&sort&order&limit&offset` | SQL filtering, sorting and paging; slim rows (`ExperimentSummary`); the console keeps the filters in the URL. |
| Dashboard | `GET /dashboard/summary` | Counts by state and outcome group, current-version score statistics, recovery and outage distributions, score history, namespaces, recent runs. |
| Services | `GET /services`, `GET /services/{ns}/{kind}/{name}` | Live workloads outside system namespaces joined with exact-target history; the detail view adds live pod status, tested faults and score history. |

## 14. Manual (step-by-step) mode

The manual endpoints exist for operators and tests. They are not used by the console's
start flow, which uses `/run`.

| Step | Endpoint | Note |
|---|---|---|
| Validate | `POST /experiments/{id}/validate` | Also used by the console before `/run`. |
| Baseline | `POST /experiments/{id}/baseline` | |
| Inject | `POST /experiments/{id}/inject` | Blocks up to ~15 s on kind (`run_injection` polling). |
| Observe | `POST /experiments/{id}/observe` | One bounded step per call; the client polls. |

All manual endpoints return 409 for auto-driven experiments (`_manual_only`).

---

## Related documents
[03-system-architecture](03-system-architecture.md) · [06-safety-framework](06-safety-framework.md) · [07-evidence-framework](07-evidence-framework.md) · [08-recovery-framework](08-recovery-framework.md) · [09-scoring-methodology](09-scoring-methodology.md)

## Missing information
- End-to-end timing distributions per phase (how long validation, baseline and observation take) have not been measured systematically. The only figure is B2: "COMPLETED in 101 s" for one automatic sandbox run.

## Open questions
- Should the paper present the manual mode at all? Recommended: one sentence; the evaluation should use `/run` only.
