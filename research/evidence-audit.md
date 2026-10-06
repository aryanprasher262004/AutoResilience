# AutoResilience Research Evidence Audit

Read-only audit of repository commit `72be555` and the local environment, 2026-10-07 (UTC).
No application code, database row or cluster object was changed; no experiment was run.
Machine-readable data: `research/experiment-results.json` (full records, raw episodes, raw
Litmus objects) and `research/experiment-results.csv` (one row per real run).

**Most important finding.** The AutoResilience database contains **0 experiments**. Every
development-verification run was recorded in temporary databases that were deleted during
cleanup. What survives is (1) six LitmusChaos objects created by AutoResilience, (2) raw
Prometheus telemetry of the client and cluster during the runs, and (3) numbers recorded in
committed docs. All three are real, but none is a complete AutoResilience record. **The
Results section needs a new, controlled experiment campaign (§M).** Prometheus keeps raw data
for only 2 days on ephemeral storage: the telemetry extracted here expires around
2026-10-08T11:14Z, or earlier if the Prometheus pod restarts.

## A. Final System Summary

AutoResilience is a self-service resilience-testing platform for Kubernetes. A user picks a
workload and a pod-delete fault in a web console. The backend validates it against
namespace-scoped safety policies and the live cluster, captures a Prometheus baseline,
injects the fault through LitmusChaos, and observes impact from three angles: Kubernetes
state, server metrics, and a client load generator. It decides recovery with an explicit
rule, and computes an explainable Resilience Score (v3, 0–100). An in-process reconciler
drives the whole lifecycle after a single `POST /experiments/{id}/run`. Results are browsable
as history, per-service views and printable reports.

## B. Architecture

```
Browser ── Next.js console (/api/backend/* rewrite) ── FastAPI API ── PostgreSQL (experiments)
                                                          │  ├─ Reconciler thread (orchestrator, 5 s tick)
                                                          │  ├─ KubernetesAdapter (read-only)  ──┐
                                                          │  ├─ PrometheusClient (read-only GET) ─┤ kind cluster "autoresilience"
                                                          │  └─ LitmusChaosProvider (only writer:  │  ├─ litmus: chaos-operator
                                                          │       own ar-<id> ChaosEngines)  ─────┘  ├─ monitoring: Prometheus + kube-state-metrics
                                                          │                                          ├─ shop: frontend, checkout, cart-redis, loadgen
                                                          │                                          └─ resilience-sandbox: fragile
```

| Component | Implementation | Role |
|---|---|---|
| Frontend | `apps/web` (Next.js App Router, TanStack Query) | Builder, live room, history, reports, services, readiness status. Polls the API: 3 s while a run is active. |
| Backend | `apps/api` (FastAPI, SQLAlchemy 2, Alembic) | API, safety validation, orchestration, evidence and scoring. |
| PostgreSQL | `experiments` table; evidence as JSON columns (`validation_result`, `baseline`, `chaos`, `observation`, `score`, `orchestration`) | System of record. |
| Kubernetes | kind, single node | Target environment. |
| Prometheus | server + kube-state-metrics, 15 s scrape | Baseline, observation and recovery evidence. |
| LitmusChaos | litmus-core operator, vetted `pod-delete` ChaosExperiment (go-runner) | Fault injection. |
| Load generator | `infra/sample-app/loadgen/loadgen.py` (stdlib Python, ConfigMap) | Client-side truth: per-outcome counters and outage duration. |
| Orchestration | `services/orchestration/orchestrator.py` | Stateless, restart-safe reconciler. Deadlines, abort, label-verified cleanup. |
| Recovery | `services/orchestration/recovery.py` (pure) | Recovery rule (§H). |
| Scoring | `services/scoring/resilience_score.py` (pure, no I/O) | v1, v2 and v3; v3 is current (§I). |

## C. Technology Stack

| Layer | Version (source) |
|---|---|
| Python | 3.12.13 (requires ≥ 3.12) |
| FastAPI / Starlette / Pydantic | 0.141.1 / 1.6.0 / 2.13.4 (`uv.lock`) |
| SQLAlchemy / psycopg / Alembic | 2.0.52 / 3.3.4 / 1.19.1; DB schema revision `08697f19aec0` |
| kubernetes (Python client) / uvicorn / httpx | 36.0.3 / 0.52.3 / 0.28.1 |
| PostgreSQL | `postgres:17-alpine` (`scripts/dev-db.sh`, CI) |
| Node.js | 24.13.1 locally, 24 in CI |
| Next.js / React / TanStack Query | 16.3.8 / 19.2.8 / 5.104.1 |
| Tailwind CSS / TypeScript / openapi-typescript | 4.3.3 / 5.9.3 / 7.13.0 |
| Tests | pytest 9.1.1, ruff 0.16.3, mypy 2.3.1; Vitest 4.1.11, happy-dom 20.14.5, Testing Library 16.3.3 |
| kind / node image | v0.33.0 / `kindest/node:v1.37.0` (Kubernetes v1.37.0, containerd 2.3.4, Debian 13) |
| kubectl / Helm / Docker Engine | client v1.35.3 / v4.3.0 / 29.3.1 |
| Prometheus | 3.15.0, chart `prometheus` 29.35.0, retention 2d, no persistent volume |
| kube-state-metrics | v2.20.0 |
| LitmusChaos | chart `litmus-core` 3.31.1, chaos-operator 3.31.0, `go-runner:3.31.0` |
| Sample images | `ghcr.io/stefanprodan/podinfo:6.9.2`, `nginx:1.27-alpine`, `redis:7-alpine`, `python:3.12.11-alpine3.22` |
| kube-proxy | iptables mode |
| Host resources | node capacity 10 CPU, 8,024,472 KiB memory (Docker VM). The host machine model is not recorded. |

## D. Kubernetes Environment

Cluster `autoresilience` (context `kind-autoresilience`), one control-plane node
`autoresilience-control-plane`. Prometheus NodePort 30090 is mapped to `127.0.0.1:9090`.

| Namespace | Workload | Kind | Replicas | Image | Selector | Notes |
|---|---|---|---|---|---|---|
| shop | frontend | Deployment | 3 | nginx 1.27 | `app=frontend` | readiness `/` every 10 s; no request metrics |
| shop | checkout | Deployment | 2 | podinfo 6.9.2 | `app=checkout` | `http_requests_total` scraped (port 9797); readiness `/readyz` every 10 s |
| shop | cart-redis | StatefulSet | 1 | redis 7 | `app=cart-redis` | no client or request metrics |
| shop | loadgen | Deployment | 1 | python 3.12.11 | `app=loadgen` | client load generator; metrics on 9100 |
| resilience-sandbox | fragile | Deployment | 1 | podinfo 6.9.2 | `app=fragile` | readiness `initialDelaySeconds: 10`, period 1 s (modelled warm-up); namespace label `autoresilience.io/sandbox=true` |
| monitoring | prometheus-server, prometheus-kube-state-metrics | Deployment | 1 / 1 | | | system |
| litmus | litmus (chaos-operator) | Deployment | 1 | | | system |
| kube-system, local-path-storage | coredns (2), local-path-provisioner (1) | Deployment | | | | system |

- **Services (ClusterIP):** `frontend:80`, `checkout:80→9898`, `cart-redis:6379`, `fragile:80`.
- **Termination grace:** 30 s for all sample pods. Rollout strategy: RollingUpdate.
- **Load generator:**
  - targets `shop/checkout`, `shop/frontend` and `resilience-sandbox/fragile`;
  - one sequential request every 0.1 s (10 req/s) per target, 1 s timeout;
  - outcomes: `success`, `http_error` (≥ 500), `connection_error`, `timeout`.
- **Chaos namespaces:** `shop` and `resilience-sandbox` each hold the `pod-delete` ChaosExperiment and the `autoresilience-chaos` ServiceAccount, whose Role can only delete pods in its own namespace.
- **Six old ChaosEngines/ChaosResults:** still present in `resilience-sandbox` (§K). Their DB records were lost, so the orchestrator never cleaned them up.

## E. Experiment Lifecycle

States (`domain/state_machine.py`), with explicit allowed transitions:

```
CREATED → VALIDATING → BASELINING → INJECTING → OBSERVING → RECOVERING → COMPLETED
             └→ VALIDATION_FAILED       └→ INJECTION_FAILED
Any of CREATED…RECOVERING → ABORTED;  BASELINING/INJECTING/OBSERVING/RECOVERING → UNKNOWN;  UNKNOWN → ABORTED
Terminal: COMPLETED, VALIDATION_FAILED, INJECTION_FAILED, ABORTED and, in practice, UNKNOWN: the state machine allows UNKNOWN → ABORTED, but the orchestrator treats UNKNOWN as terminal and its ABORTABLE set excludes it, so that edge is unreachable through the API
```

- **Driving it:** `POST /run` sets `orchestration.mode="auto"`. The reconciler then advances one bounded step per 5 s tick. Manual step endpoints still exist and return 409 for auto runs.
- **Deadlines:**

  | Phase | Default | On expiry |
  |---|---|---|
  | Baseline | 180 s | UNKNOWN `BASELINE_TIMEOUT` |
  | Chaos start | 120 s | INJECTION_FAILED |
  | Observation | duration + 180 s | UNKNOWN `LITMUS_TIMEOUT` |
  | Recovery | 300 s after Litmus finishes | UNKNOWN |
  | Whole run | 1,800 s | UNKNOWN `ORCHESTRATION_TIMEOUT` (or ABORTED before baseline) |

- **Restart safety:** all progress lives in PostgreSQL, so a restarted API resumes.
- **Engine identity:** each engine is named `ar-<id>`, so a run is never injected twice.
- **Cleanup:** finished runs' engines and ChaosResults are deleted only after re-reading their labels (`managed-by=autoresilience`, `experiment-id`).
- **UNKNOWN outcomes** carry a `reason_code` and a `cause`:

  | Cause | Reason codes |
  |---|---|
  | `platform` | `LITMUS_UNREADABLE`, `LITMUS_ERROR`, `LITMUS_TIMEOUT`, `PROMETHEUS_UNAVAILABLE`, `INSUFFICIENT_DATA` (no samples, or gaps > 40 s) |
  | `conflicting_evidence` | `LITMUS_VERDICT_FAIL` (recovery seen, but Litmus failed) |
  | `application` | `RECOVERY_NOT_OBSERVED` |

## F. Safety Mechanism

**Policies.** Code-defined (`domain/safety_policy.py`), selected **only** by the target
namespace. No API field can choose or alter a policy.

| Policy | Applies to | max duration | max affected replicas | min healthy replicas after fault | Namespaces |
|---|---|---|---|---|---|
| `default` | every namespace except the sandbox | 300 s | 1 | 1 | forbidden: `kube-system, kube-public, kube-node-lease, local-path-storage, litmus, monitoring` |
| `sandbox` | `resilience-sandbox` | 300 s | 1 | **0** | allowlist: `resilience-sandbox` only |

**Checks.** Each has status `PASSED | FAILED | ERROR | SKIPPED`; only all-PASSED proceeds.
- **Static:** `fault_type_supported` (pod-delete only), `namespace_not_forbidden`, `namespace_allowed`, `duration_within_limit`, `affected_replicas_within_limit`.
- **Cluster** (only queried if the static checks pass; a Kubernetes error becomes ERROR, never a pass):
  - `target_workload_exists`;
  - `target_has_running_pods`;
  - `min_healthy_replicas_after_fault` (ready − affected ≥ minimum).

**At injection time:**
1. The policy is re-resolved and must equal the validated one.
2. The cluster checks are re-run.
3. Targets are the first N ready pods by name.
4. The provider independently refuses system namespaces.
5. The ChaosEngine is built only from typed fields (no user YAML).

**After injection:**
- `OBSERVING` is entered only once Litmus is running **and** the target pods are gone or terminating.
- **Abort** stops only the run's own engine.

**Not implemented:** automatic abort on live signals (`services/safety/live_monitor.py` is a placeholder).

## G. Evidence Collection

**Baseline** (`services/orchestration/baseline.py`): instant queries over a 300 s window.

| Group | Required | Content | Notes |
|---|---|---|---|
| availability | yes | desired, avg/min/count of available replicas | needs ≥ 4 samples |
| restarts | yes | restart counts | |
| requests | no | `http_requests_total` rate and 5xx ratio | UNAVAILABLE if the target exposes no such metric |
| client | no | load generator rate, failure ratio, p95, outage seconds and outage transitions | |

Only a `CAPTURED` baseline moves the run to INJECTING.

**Observation** (`observation_queries`): `W` = seconds since the ChaosEngine was created.

| Evidence | Source | Precision |
|---|---|---|
| Client per-outcome counts | raw counter samples, from the last scrape before the fault | exact |
| Client outage seconds and transitions | raw counters | exact |
| Outage windows | client's own start/end timestamp gauges | client timestamps |
| Outage pattern | derived | `NONE`, `CONTINUOUS`, `INTERMITTENT` or `INSUFFICIENT_DATA` (e.g. a counter reset) |
| Availability | raw scrape samples, so data gaps stay visible | 15 s |
| Replacement pods | `kube_pod_created` / `kube_pod_status_ready_time` | 1 s |
| Restarts, server requests and 5xx | Prometheus | |
| Litmus | engine status, verdict and ChaosResult | |

Stored in `experiments.observation`.

## H. Recovery Detection

A target counts as recovered only when all three criteria hold
(`recovery.py`; defaults from `core/config.py`):

1. **Replacement.** At least `affected_replicas` pods created after the fault became Ready.
   - The recovery instant is the Ready time of the N-th replacement, at 1 s resolution.
   - `time_to_recovery = Ready − created`, i.e. replacement start-up time. It does not include client reconvergence.
2. **Sustained.** At least 4 consecutive raw availability samples at or above the baseline's desired replicas, all after the recovery instant, with no gap over 40 s.
3. **Requests.** Only if the baseline had server traffic: requests must flow in the stable window, with a 5xx ratio ≤ baseline + 0.01.

Recovered **and** Litmus Pass → COMPLETED. Recovered but Litmus not Pass →
UNKNOWN/`conflicting_evidence`. Not recovered by the deadline → UNKNOWN (§E).

## I. Resilience Score v3

Inputs come only from stored evidence; the scorer is pure, with no I/O. Only COMPLETED and
UNKNOWN runs with a baseline and an observation are scored.

**Formula:**
- Each component *i* has a normalized value n_i ∈ [0, 1] and weight w_i.
- Components that are NOT_APPLICABLE are dropped, and the remaining weights are re-normalized to 100: w′_i = w_i / Σ w_applicable × 100.
- `score = round(Σ n_i · w′_i, 1)`.
- Not recovered (application UNKNOWN): `score = min(score, 40)`, status `SCORED_NOT_RECOVERED`.

**Rating:** Excellent ≥ 90, Good ≥ 75, Fair ≥ 50, Poor < 50.

`lin(x; a, b)` = 1 if x ≤ a, 0 if x ≥ b, otherwise 1 − (x − a)/(b − a), rounded to 4 decimals.

| Component | Weight | Normalization (v3) | Missing data |
|---|---|---|---|
| recovery_time | 35 | lin(time_to_recovery; 10 s, 120 s); 0 if not recovered | — |
| client_outage | 15 | excess = max(0, measured − baseline_outage/baseline_window × window); lin(excess; 1 s, 60 s) | Falls back to sampled availability, min(available)/desired (`[fallback: …]`), if there is no client data, no requests, or the client data is not OK. NOT_APPLICABLE if there are no availability samples either. |
| request_failures | 30 | client failure-ratio increase over baseline; lin(increase; 0.001, 0.05) | Falls back to the server 5xx ratio increase (same thresholds). NOT_APPLICABLE if neither exists. On the server fallback, zero requests despite baseline traffic gives 0. |
| restarts | 10 | max(0, 1 − restarts/2) | NOT_APPLICABLE without restart data |
| litmus_verdict | 10 | 1 if Pass, otherwise 0 | — |

**Undetermined outcomes:**
- Platform or conflicting-evidence UNKNOWN → `NOT_SCORED` (`score: null`).
- Application UNKNOWN → scored with recovery = 0, then capped at 40.
- Incomplete observation evidence → `NOT_SCORED`.

**Versioning:** every score stores its version, weights, thresholds and per-component reasons.
v1 and v2 can be recomputed from the same evidence with `GET /experiments/{id}/score?version=`:

| Version | Weights | Difference from the previous version |
|---|---|---|
| v1 | 35 / 25 / 20 / 10 / 10 | availability; server-side error ratio |
| v2 | 35 / 15 / 30 / 10 / 10 | client request failures replace the server error ratio |
| v3 | 35 / 15 / 30 / 10 / 10 | measured client outage replaces sampled availability |

The scoring, observation, recovery and baseline code and the sample manifests are unchanged
from commit `e1b6923` (v3, 2026-10-06T11:28Z) to HEAD.

## J. Frontend Usage Flow

| Step | Screen / API |
|---|---|
| Configure | `/experiments/new`. Name; target picked from discovered workloads (`GET /services`) or typed; fault, mode, duration, affected replicas. Client checks are limited to required and positive-integer; server 422s are mapped onto fields. |
| Safety | `POST /experiments` then `POST /experiments/{id}/validate`. The server's static and cluster checks and the policy are shown as returned. A blocked run is recorded as VALIDATION_FAILED. |
| Review | The stored configuration plus a warning; an explicit confirmation checkbox is required. |
| Run | `POST /experiments/{id}/run`, then a redirect to the room. |
| Live room | `/experiments/{id}`, polling every 3 s until terminal: lifecycle, live status, fault → impact → recovery, metrics, events, raw evidence. Abort (with a reason) is available in active states. |
| Result | Outcome banner and score panel (score, rating, per-component points lost, NOT_SCORED explanation). |
| Report | `/reports/{id}`: summary, configuration, safety checks, baseline and measurements, impact and recovery, score. Printable (print / save as PDF). |

Supporting pages: `/` (aggregates from `GET /dashboard/summary`), `/experiments` (server-side
history filters), `/services`, `/settings`, and a sidebar readiness status from `GET /ready`.

**Experiment-related API:**
- Experiments: `POST/GET /experiments`, `GET /experiments/{id}`, `POST /experiments/{id}/{validate|baseline|inject|observe|run|abort}`, `GET /experiments/{id}/score`, `GET /experiments/history`.
- Dashboard and services: `GET /dashboard/summary`, `GET /services`, `GET /services/{ns}/{kind}/{name}`.
- Health: `GET /health`, `GET /ready`.

## K. Existing Real Experimental Evidence

Categories are kept separate in the JSON (`evidence_category`).

**K1. AutoResilience database records: none** (0 rows).

**K2. Real API runs with partial records (6), identified by surviving ChaosEngines.** All six:
- target `resilience-sandbox/fragile`, 1 replica, pod-delete, 30 s, 1 affected replica;
- Litmus `Completed` / `Pass`.

Recovery is from pod timestamps; client failures are re-derived from raw counters;
documented values come from the committed docs.

| Run | Template | Mode | Created→Ready | Client failures | Outage | Documented scores |
|---|---|---|---|---|---|---|
| `9d95d794` 10:51Z | no warm-up | GRACEFUL | 0 s | 0 | (not instrumented) | 100 (version not stated) |
| `e89d2585` 10:52Z | no warm-up | FORCE | 1 s | 0 | (not instrumented) | 100 (version not stated) |
| `d406ca22` 10:58Z | 10 s warm-up | GRACEFUL | 11 s | 19 (13 conn, 6 timeout) | (not instrumented) | v2 71.2, v1 74.7 |
| `4a44f687` 11:05Z | 10 s warm-up | FORCE | 10 s | 22 (14 conn, 8 timeout) | (not instrumented) | v2 80.5, v1 100.0 |
| `66d86b9a` 11:19Z | 10 s warm-up | GRACEFUL | 11 s | 20 (13 conn, 7 timeout) | 8.358 s, CONTINUOUS | **v3 80.4**, v2 67.2, v1 74.7 |
| `7ea2e0f7` 11:26Z | 10 s warm-up | FORCE | 10 s | 23 (15 conn, 8 timeout) | 10.479 s, CONTINUOUS | **v3 76.8**, v2 79.2, v1 100.0 |

The re-derived failure counts and outage windows match the docs exactly, which is an
independent consistency check.

**K3. Real disruptions not attributable to a run (16), from post-hoc telemetry only.**
These are single-pod replacements with an unchanged pod template, recorded during
development-verification windows between commits `29d493d` and `74d064c`. Each
is consistent with an AutoResilience pod-delete run, but its run id, mode, validation,
baseline and score are **unknown**.
- **13 on `fragile`** (1 replica, 10 s warm-up).
- **3 on `checkout`** (2 replicas): created → Ready 1 s, 0 client failures, outage 0 s (pattern NONE), sampled availability 2/2.

**K4. Runs documented in committed docs only (6, no raw data):**
- `shop/checkout`, three runs:
  - the v1 worked example: 100.0;
  - v2 GRACEFUL: 740 requests, 0 failed, 100.0;
  - v2 FORCE: 739 requests, 0 failed, 100.0.
- Orchestration verification on `fragile`, three runs:
  - automatic run: COMPLETED in 101 s, v3 85.8;
  - restart-resume run: COMPLETED;
  - abort-in-OBSERVING run: ABORTED.

  These three probably correspond to three of the 11:39–11:48Z episodes, but that is unverified.

**K5. Manual infrastructure probe (1, not an experiment):** `checkout` scaled to 0 for about
20 s produced 23 connection errors and 17 timeouts at the client (instrument sensitivity check).

**Aggregate observations usable now, with caveats (§P):**

| Population | n | Created→Ready (s) | Client failures | Client outage (s) |
|---|---|---|---|---|
| fragile, 10 s warm-up, all modes (K2 + K3) | 17 runs; outage measured for 15 | 10–11, median 10, mean 10.47, sd 0.51 | 18–24, median 20, mean 20.18, sd 1.63 | 7.239–10.565, median 8.358, mean 8.43, sd 1.03 |
| fragile without warm-up | 2 | 0–1 | 0 | — |
| checkout, 2 replicas | 3 (K3) + 2 (K4 v2) | 1 | 0 | 0 (for the 3 K3 runs) |

**Sampled-availability blind spot.** Fifteen-second Kubernetes availability sampling registered
the dip in only **9 of 17** fragile disruptions (53%). The client recorded failures in **17 of 17**
and a measured outage in all 15 instrumented runs. The expected detection rate is about
outage / scrape interval ≈ 8.4 / 15 ≈ 56%. This is the empirical motivation for v3.

## L. Existing Test/Fixture Evidence (not experimental evidence)

- **Backend: 431 pytest tests.**
  - In-memory SQLite.
  - Fakes: `FakeKubernetes`, `FakePrometheus` (synthetic samples), `FakeChaos` (scripted Litmus statuses).
  - Coverage: state machine; safety policy and evaluator; read-only adapter; Prometheus client; baseline; recovery rule; client outage; v1/v2/v3 scoring; orchestration (restart, abort, cleanup, deadlines); history, dashboard, services, readiness and DB-error APIs.
- **Frontend: 39 Vitest tests** with contract-typed fixtures (`apps/web/src/test/fixtures.ts`). Its score values (e.g. 83.6) imitate real responses but are **fixtures** and must not be reported as results.
- **CI:** five GitHub Actions jobs (backend, migrations on PostgreSQL 17, frontend, frontend tests, contract drift). They have not yet run on GitHub (nothing pushed).

Tests support a correctness or verification claim, not a performance claim.

## M. Recommended Final Experiment Matrix (not run)

**Preconditions:**
- A persistent DB (`scripts/dev-db.sh`), with no rebuilds between runs.
- An export of `GET /experiments/{id}` and `GET /experiments/{id}/score?version=v1|v2` for every run into `research/raw/`.
- A `pg_dump` after each block.
- A Prometheus snapshot, or extending retention, during the campaign.
- Runs spaced **≥ 6 min apart**, so the 300 s baseline window never contains the previous run's outage.
- Record the commit and environment per block.

| Block | Target (policy) | Factor levels | Reps | Purpose |
|---|---|---|---|---|
| E1 | `resilience-sandbox/fragile` (sandbox), 1 replica | GRACEFUL, FORCE | 10 each | single-replica outage, recovery and score; mode effect |
| E2 | `shop/checkout` (default), 2 replicas | GRACEFUL, FORCE | 10 each | redundancy masks client impact |
| E3 | `shop/frontend` (default), 3 replicas (nginx, no request metrics) | GRACEFUL, FORCE | 5 each | server-metrics-absent path; generality across images |
| E4 | fragile warm-up ablation (`initialDelaySeconds` 0 / 5 / 10 / 20; manifest change per level) | GRACEFUL | 5 per level | score sensitivity to a controlled recovery delay |
| S1 | safety blocks: `kube-system/coredns`; checkout with affected = 2; `shop/cart-redis` (1 replica, default policy); duration 600 s; a non-existent workload | — | 3 each | every check produces the expected FAILED/blocked outcome; no cluster change |
| R1 | robustness: abort in OBSERVING; API restart in OBSERVING; Litmus timeout via `OBSERVATION_GRACE_SECONDS=1` | — | 3 each | ABORTED, resume → COMPLETED, UNKNOWN/NOT_SCORED; no duplicate engines |
| C1 | instrument calibration: scale fragile to 0 for 5 / 10 / 20 / 30 s (manual probe, outside AutoResilience) | — | 3 each | client-measured outage vs ground-truth duration |
| V1 | score-version comparison: recompute v1, v2 and v3 for E1–E4 from stored evidence | — | (no runs) | sampled availability vs measured outage |

E1–E4 plus S1, R1 and C1 come to 106 runs: 79 AutoResilience fault runs (E1–E4, R1) at ~6–8 min each when spaced, about 8–10.5 h; 15 safety blocks (seconds each, no injection); 12 manual calibration probes.

## N. Required Tables

1. Technology stack and versions (§C).
2. Kubernetes topology (§D).
3. Safety policies and checks (§F).
4. State machine transitions and outcome codes (§E).
5. Score v3 components, weights, thresholds and fallbacks, plus v1/v2/v3 differences (§I).
6. Per-block results: mean ± sd and median of time to recovery, client outage, client failures and the v3 score, with ratings (E1–E4).
7. v1 / v2 / v3 scores on identical evidence (V1).
8. Safety-validation outcomes per scenario (S1).
9. Robustness outcomes (R1).
10. Instrument calibration (C1).
11. Sampled-availability vs client detection rates.

## O. Required Figures

1. Architecture diagram (§B).
2. Lifecycle state diagram (§E).
3. End-to-end sequence: console → API → reconciler → Litmus/Prometheus.
4. Single-run timeline: fault start, pod deletion, outage window, replacement Ready, stability samples, final state. The 11:19Z run can serve as an illustration once re-run.
5. Box plots of client outage and failures per block and mode.
6. Stacked score-component bars per block.
7. Fifteen-second scrape sampling vs a continuous client outage (the blind-spot illustration).
8. Warm-up ablation: outage and score vs `initialDelaySeconds`.
9. Console screenshots: builder safety step, live room, report.

## P. Limitations / Threats to Validity

- **Evidence provenance:** no surviving AutoResilience records. The K2 and K3 values are post-hoc re-derivations or documented numbers, and the runs used evolving development builds (code bracket per record in the JSON).
- **Environment:**
  - a single-node kind cluster on one laptop;
  - iptables kube-proxy;
  - small sample services;
  - the fragile warm-up is **modelled** (a readiness delay), not a real start-up cost.
- **Client model:** one sequential client per target at 10 req/s with a 1 s timeout.
  - Timeouts cap the number of failures counted.
  - The failure ratio is diluted by the length of the observation window.
- **Sampling:** 15 s scrapes; pod timestamps at 1 s resolution; outage resolution of one request interval (0.1 s, or up to 1 s during timeouts).
- **Baseline contamination:** back-to-back runs (< 300 s apart) put the previous outage into the baseline. v3 subtracts that "expected" outage, which inflates scores. Seven of the K3 fragile runs are affected.
- **Litmus verdict:** no Litmus probes are configured, so `Pass` only means the experiment completed. The 10-point component is nearly uninformative.
- **Score design:** weights and thresholds are author-chosen and not calibrated. A score describes one run, with no statistical aggregation. Recovery time is replacement start-up only.
- **Scope:** pod-delete only; no network, CPU or memory faults; no multi-node scheduling effects.
- **Ephemeral telemetry:** Prometheus retention is 2 days with no persistent volume.

## Q. Missing Information

- Complete AutoResilience records for every past run: validation results, stored baselines, the system's own observation windows and counts, per-component scores and reasons, final states.
- Identity, mode and score of the 16 unattributed disruptions, and mode or score for most K2 runs. v3 scores exist only for `66d86b9a` and `7ea2e0f7`.
- Exact timestamps of the K4 documented runs.
- Repeated, controlled measurements for any statistical claim; frontend and frontend-tier impact (`frontend`, `cart-redis` were never measured); calibration against ground truth.
- Host hardware model; Docker VM settings beyond the node capacity reported above.
- **Documentation inconsistencies found:**
  - `monitoring/prometheus/queries.md` and `docs/scoring/resilience-score-v2.md` list the load generator targets as checkout and frontend only; the manifest also targets `resilience-sandbox/fragile`.
  - The OpenAPI contract documents only `200`/`422` for experiment endpoints, although the API also returns 404, 409 and 503.
