# 03 · System Architecture

| | |
|---|---|
| **Purpose** | Describe the architecture of AutoResilience: high-level structure, deployment, data flow, backend, frontend, persistence, sequences and states. |
| **Source of truth** | `apps/api/app/**`, `apps/web/src/**`, `infra/**`, `chaos/**`, `monitoring/prometheus/values.yaml`, `scripts/*.sh` at `92e33dd`. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [04-component-design](04-component-design.md) (per-component detail), [05-system-workflows](05-system-workflows.md) (full sequences), [12-experimental-environment](12-experimental-environment.md) (concrete environment) |

All statements are Level C (implementation) unless marked otherwise.

---

## 1. High-level architecture

```mermaid
flowchart LR
    U([User]) --> WEB[Next.js console<br/>apps/web]
    WEB -- "/api/backend/* (rewrite)" --> API[FastAPI API<br/>apps/api]
    API <--> DB[(PostgreSQL<br/>experiments table)]
    API --> REC[Reconciler thread<br/>orchestrator.py]
    REC <--> DB
    API & REC --> KA[KubernetesAdapter<br/>read-only]
    API & REC --> PC[PrometheusClient<br/>read-only HTTP GET]
    API & REC --> CP[LitmusChaosProvider<br/>own ChaosEngines only]
    KA --> K8S[(Kubernetes API)]
    CP --> K8S
    PC --> PROM[(Prometheus)]
    subgraph Cluster [kind cluster autoresilience]
        K8S
        PROM
        KSM[kube-state-metrics] --> PROM
        LG[loadgen<br/>client] --> PROM
        LG -->|HTTP 10 req/s per target| APPS[Target workloads]
        LIT[Litmus chaos-operator] -->|pod-delete job| APPS
        APPS -->|http_requests_total| PROM
    end
    K8S --> LIT
```

**Key architectural properties (Level C):**

| Property | Where enforced |
|---|---|
| A single writer to the cluster, restricted to its own objects | `LitmusChaosProvider` creates, stops and deletes only `ar-<experiment id>` ChaosEngines and their ChaosResult |
| Read-only Kubernetes and Prometheus access | `KubernetesAdapter` uses only `read_*`/`list_*` calls (asserted in `tests/unit/test_kubernetes_adapter.py`); `PrometheusClient` only issues GET `/api/v1/query` |
| Persistent, stateless orchestration | All progress lives in `experiments` JSON columns; the reconciler re-reads state on every tick |
| Pure decision logic | `policy_evaluator.py`, `recovery.py` (`find_recovery`), `resilience_score.py` have no I/O |
| A typed contract between backend and frontend | `packages/contracts/openapi.json` → `apps/web/src/lib/api/schema.ts` (`scripts/gen-api-contracts.sh`); drift is checked in CI |

## 2. Deployment architecture

```mermaid
flowchart TB
    subgraph Host [Developer machine - macOS, Docker]
        subgraph Proc [Host processes]
            NEXT[next dev / next start :3000]
            UV[uvicorn / fastapi dev :8000]
        end
        PG[(Docker container autoresilience-postgres<br/>postgres:17-alpine :5432)]
        subgraph KIND [Docker container autoresilience-control-plane<br/>kindest/node:v1.37.0]
            subgraph ns_mon [monitoring]
                PS[prometheus-server<br/>NodePort 30090]
                KS[kube-state-metrics]
            end
            subgraph ns_lit [litmus]
                OP[chaos-operator 3.31.0]
            end
            subgraph ns_shop [shop]
                FE[frontend x3 nginx]
                CO[checkout x2 podinfo]
                CR[cart-redis x1 StatefulSet]
                LG[loadgen x1]
            end
            subgraph ns_sb [resilience-sandbox]
                FR[fragile x1 podinfo, 10 s warm-up]
            end
        end
    end
    NEXT -->|rewrite AUTORESILIENCE_API_URL| UV
    UV --> PG
    UV -->|kubeconfig context kind-autoresilience| KIND
    UV -->|127.0.0.1:9090 → NodePort 30090| PS
```

- The API and the console run **outside** the cluster as host processes.
- The API reaches the cluster through the kubeconfig context `KUBE_CONTEXT` (default: the current context), and Prometheus via the kind port mapping `127.0.0.1:9090 → 30090` (`infra/kind/cluster.yaml`).
- There is no in-cluster deployment of AutoResilience: `infra/helm` is empty, so Helm deployment of AutoResilience is not implemented.

## 3. Data flow

```mermaid
flowchart LR
    subgraph Inputs
        CFG[Experiment config<br/>POST /experiments]
    end
    CFG --> VAL[Validation<br/>static + cluster checks]
    VAL -->|validation_result JSON| DB[(experiments)]
    PROM[(Prometheus)] -->|instant queries over 300 s| BASE[Baseline capture]
    BASE -->|baseline JSON| DB
    INJ[Injection] -->|ChaosEngine ar-id| K8S[(Kubernetes / Litmus)]
    INJ -->|chaos JSON| DB
    K8S -->|engine status, verdict| OBS[Observation]
    PROM -->|raw samples since fault| OBS
    OBS -->|observation JSON:<br/>litmus, impact, recovery, result| DB
    OBS --> SCORE[Scorer v3 - pure]
    SCORE -->|score JSON| DB
    DB --> HIST[History / dashboard /<br/>services aggregation]
    DB --> UI[Console: live room, report]
    HIST --> UI
```

## 4. Backend architecture

```mermaid
flowchart TB
    subgraph API [api/routes]
        R1[experiments.py<br/>CRUD, validate, baseline, inject,<br/>observe, run, abort, score]
        R2[reports.py<br/>history, dashboard]
        R3[targets.py<br/>services]
        R4[health.py · ready.py]
        ERR[errors.py<br/>DB errors → 503]
    end
    subgraph SVC [services]
        PRE[orchestration/preflight.py]
        BAS[orchestration/baseline.py]
        INJ[orchestration/injection.py]
        OBS[orchestration/observation.py]
        RECV[orchestration/recovery.py]
        ORC[orchestration/orchestrator.py]
        PEV[safety/policy_evaluator.py]
        SCO[scoring/resilience_score.py]
        HIS[analysis/history.py]
        SRV[analysis/services.py]
        RDY[readiness.py]
    end
    subgraph DOM [domain]
        SM[state_machine.py]
        SP[safety_policy.py]
        EX[experiment.py]
    end
    subgraph INT [integrations]
        KA[kubernetes_adapter.py]
        PC[prometheus_client.py]
        CP[chaos_provider.py]
    end
    subgraph DATA [db]
        MOD[models/experiment.py]
        SES[session.py]
    end
    R1 --> PRE & BAS & INJ & OBS & ORC & SCO
    R2 --> HIS
    R3 --> SRV & KA
    R4 --> RDY
    ORC --> PRE & BAS & INJ & OBS
    OBS --> RECV & SCO
    PRE & INJ --> PEV
    PEV --> SP
    PRE & BAS & INJ & OBS & ORC --> SM
    INJ & OBS & ORC --> CP
    PRE & INJ & OBS --> KA
    BAS & OBS --> PC
    SVC --> MOD
```

**Layering rules visible in the code:**
- `domain/` has no I/O.
- `integrations/` wrap external systems and translate their errors: `ClusterUnavailableError`, `PrometheusError`, `ChaosProviderError`.
- `services/` hold lifecycle logic and accept integrations through `typing.Protocol` interfaces (`Cluster`, `Chaos`, `Metrics`, `ValueQuery`), which is why tests can inject fakes.
- Routes obtain integrations through FastAPI dependencies (`get_kubernetes_adapter`, `get_prometheus_client`, `get_chaos_provider`, `get_now`, …).

## 5. Frontend architecture

```mermaid
flowchart TB
    subgraph Routes [App Router pages - apps/web/src/app]
        P0["/ overview"]
        P1["/experiments history"]
        P2["/experiments/new builder"]
        P3["/experiments/[id] live room"]
        P4["/reports, /reports/[id]"]
        P5["/services, /services/[ns]/[kind]/[name]"]
        P6["/settings"]
    end
    subgraph Comp [components]
        BLD[experiment/builder/*]
        ROOM[experiment/room/*]
        HV[history/history-view]
        OV[overview/*]
        RV[report/report-view]
        SV[services/*]
        SH[shell: sidebar, top-bar, api-status]
        UIK[ui primitives]
    end
    subgraph Lib [lib]
        CL[api/client.ts<br/>fetch + ApiError]
        Q[api/queries.ts<br/>TanStack Query hooks + polling]
        T[api/schema.ts generated<br/>api/types.ts aliases]
        EV[evidence.ts<br/>runtime-checked JSON readers]
        ST[experiment-state.ts<br/>STATE_META, presentState]
    end
    Routes --> Comp --> Q --> CL -->|/api/backend/*| API[(FastAPI)]
    Comp --> EV & ST
    CL --> T
```

- **Data access:** all through TanStack Query hooks with polling:
  - one experiment: 3 s while non-terminal;
  - lists: 3 s while a run is active, otherwise 15 s;
  - dashboard: 5 s or 15 s;
  - services: 15 s;
  - readiness: 15 s when ready, 5 s otherwise.
- **Evidence JSON** (free-form backend dictionaries) is read only through `lib/evidence.ts`. A missing field becomes `null` and is shown as "No data", never invented.
- **No server-side rendering of data:** pages are client components fetching the API.

## 6. Persistence architecture

One table, `experiments` (`apps/api/app/db/models/experiment.py`). Typed columns hold the
configuration; JSON columns hold the evidence of each lifecycle phase.

```mermaid
erDiagram
    EXPERIMENTS {
        uuid id PK
        string name
        text description
        string state "11-value enum, indexed"
        string target_namespace
        string target_kind "Deployment|StatefulSet"
        string target_name
        string fault_type
        int duration_seconds
        int affected_replicas
        string pod_delete_mode "GRACEFUL|FORCE"
        json validation_result "checks, policy, policy_selection"
        json baseline "groups: availability, restarts, requests, client"
        json chaos "engine, target_pods, status, failure"
        json observation "litmus, impact, recovery, result"
        json score "version, components, explanation"
        json orchestration "mode, state_since, events, result, abort, cleanup"
        timestamptz created_at
        timestamptz updated_at
    }
```

Migration chain (Alembic, `apps/api/alembic/versions/`):
`d212b6a34d8b` create table → `90b79844b9cf` target, fault and validation → `d369e0debbe0` baseline → `98573305f15d` chaos → `d43ecd782a89` observation → `0363e45a3d5b` score → `000336cc0672` pod_delete_mode → `08697f19aec0` orchestration (head).

The JSON shapes are specified in [appendix/experiment-json-schema](appendix/experiment-json-schema.md).

## 7. End-to-end sequence (automatic run)

```mermaid
sequenceDiagram
    actor User
    participant UI as Console
    participant API as FastAPI
    participant DB as PostgreSQL
    participant R as Reconciler (5 s tick)
    participant K as Kubernetes
    participant P as Prometheus
    participant L as Litmus
    User->>UI: Configure (target, mode, duration, replicas)
    UI->>API: POST /experiments
    API->>DB: insert (CREATED)
    UI->>API: POST /experiments/{id}/validate
    API->>K: read workload + pods
    API->>DB: validation_result, BASELINING or VALIDATION_FAILED
    User->>UI: confirm + Start
    UI->>API: POST /experiments/{id}/run (202)
    API->>DB: orchestration.mode = auto
    loop every tick until terminal
        R->>DB: load auto experiments
        alt BASELINING
            R->>P: baseline queries (300 s)
            R->>DB: baseline, INJECTING if CAPTURED
        else INJECTING
            R->>K: re-check workload (policy, replicas)
            R->>L: create ChaosEngine ar-id (TARGET_PODS)
            R->>L: poll engine status
            R->>K: are target pods gone?
            R->>DB: chaos, OBSERVING
        else OBSERVING
            R->>L: engine status / verdict / ChaosResult
            R->>DB: RECOVERING when Litmus finished
        else RECOVERING
            R->>P: raw availability, pod times, client counters
            R->>DB: observation + score, COMPLETED or UNKNOWN
        end
    end
    R->>L: delete own engine + result (label-verified)
    UI->>API: GET /experiments/{id} (poll 3 s)
    UI-->>User: live room → result → /reports/{id}
```

## 8. Experiment state diagram

```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> VALIDATING
    VALIDATING --> BASELINING: all checks PASSED
    VALIDATING --> VALIDATION_FAILED: any FAILED/ERROR
    BASELINING --> INJECTING: baseline CAPTURED
    BASELINING --> UNKNOWN: BASELINE_TIMEOUT / ORCHESTRATION_TIMEOUT
    INJECTING --> OBSERVING: Litmus running and target pods gone
    INJECTING --> INJECTION_FAILED: re-check failed, Litmus failed, timeout
    INJECTING --> UNKNOWN: ORCHESTRATION_TIMEOUT
    OBSERVING --> RECOVERING: Litmus Completed (Pass/Fail)
    OBSERVING --> UNKNOWN: LITMUS_ERROR / LITMUS_TIMEOUT / LITMUS_UNREADABLE
    RECOVERING --> COMPLETED: recovery rule met and Litmus Pass
    RECOVERING --> UNKNOWN: not recovered / conflicting / no data
    CREATED --> ABORTED
    VALIDATING --> ABORTED
    BASELINING --> ABORTED
    INJECTING --> ABORTED
    OBSERVING --> ABORTED
    RECOVERING --> ABORTED
    COMPLETED --> [*]
    VALIDATION_FAILED --> [*]
    INJECTION_FAILED --> [*]
    ABORTED --> [*]
    UNKNOWN --> [*]
```

The state machine (`domain/state_machine.py`) also defines `UNKNOWN → ABORTED`, but
`orchestrator.py` treats UNKNOWN as terminal and `ABORTABLE` excludes it. The edge is
therefore **unreachable through the API** ([08](08-recovery-framework.md) §5).

## 9. Component summary

| Component | Purpose | Responsibilities | Inputs | Outputs | Dependencies | Failure modes (and handling) |
|---|---|---|---|---|---|---|
| Web console | Self-service UI | Configure, validate, run, follow, abort, browse history, services and reports | User input; API JSON | HTTP requests | API via rewrite | API unreachable → "API unreachable"; DB down → 503 message; readiness indicator ([04](04-component-design.md) §1) |
| Experiment API | System boundary | Validation of input (Pydantic), lifecycle endpoints, history and services, readiness | HTTP JSON | Experiment JSON | DB, integrations | 422 invalid input; 404 unknown id; 409 wrong state or auto-driven; 503 DB or cluster unavailable |
| Reconciler | Automatic lifecycle | One bounded step per tick per auto experiment; deadlines; cleanup | DB state, clock | State transitions, evidence | All integrations | Step exception → `orchestration.last_error`, retried next tick; deadlines → UNKNOWN/ABORTED |
| Safety evaluator | Gatekeeping | Static and cluster checks | Spec, policy, workload status | Check list | Policy, adapter | Cluster error → ERROR (never PASSED) |
| Kubernetes adapter | Cluster facts | Workload status, ready pods, live pods, workload list | kubeconfig context | `WorkloadStatus` | Kubernetes API | `ClusterUnavailableError`; 404 → `None` |
| Prometheus client | Metrics | Instant and range-vector queries | PromQL | Samples, series | Prometheus HTTP | `PrometheusError` on any failure |
| Chaos provider | Fault injection | Create, poll, stop and delete own engines | `PodDeleteRequest` | Engine name, status, result | Kubernetes custom objects | `ChaosProviderError`, `ChaosEngineExistsError`; system namespaces refused |
| Recovery analyzer | Recovery decision | `find_recovery`, client counts, outage pattern | Raw samples, pod times | `RecoveryFinding`, impact | None (pure) | Insufficient data → reported, not guessed |
| Scorer | Explainable score | v1/v2/v3 computation | State, baseline, observation, chaos | Score dict | None (pure) | NOT_SCORED with reason |
| Database | System of record | Persist experiments and evidence | ORM | Rows | PostgreSQL | Unreachable → 503 + `/ready` not_ready |
| Readiness | Operability | DB reachable and at the migration head | DB | `ready` / `not_ready` | DB, Alembic scripts | 503 with a reason code |

---

## Related documents
[04-component-design](04-component-design.md) · [05-system-workflows](05-system-workflows.md) · [10-implementation](10-implementation.md) · [12-experimental-environment](12-experimental-environment.md) · [appendix/repository-map](appendix/repository-map.md)

## Missing information
- No architecture diagram assets exist in the repository (`assets/` referenced by `README.md` is absent).
- In-cluster deployment of AutoResilience: not implemented.

## Open questions
- For the paper, should the deployment view show the evaluation setup (host processes plus kind) or an idealised in-cluster deployment? Recommended: the actual evaluation setup only.
