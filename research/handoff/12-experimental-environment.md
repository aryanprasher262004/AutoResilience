# 12 · Experimental Environment

| | |
|---|---|
| **Purpose** | A complete, reproducible description of the environment for experiments: hardware, software, cluster, namespaces, applications, replicas, policies, Prometheus, Litmus, load generator, database, configuration, and setup procedure. |
| **Source of truth** | `infra/**`, `chaos/**`, `monitoring/prometheus/values.yaml`, `scripts/*.sh`, `apps/api/app/core/config.py`; live cluster inspection on 2026-10-07 (read-only). |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [11-technology-stack](11-technology-stack.md), [appendix/kubernetes-topology](appendix/kubernetes-topology.md), [06-safety-framework](06-safety-framework.md) |

---

## 1. Hardware

| Item | Value | Source |
|---|---|---|
| kind node capacity | 10 CPU, 8,024,472 KiB memory (≈ 7.65 GiB) | `kubectl get node … .status.capacity` (observed) |
| Host machine | macOS (Darwin 25.6.0), Apple Silicon (arm64, from `kind version`: `darwin/arm64`) | Observed |
| Host CPU or RAM model | Not verified from implementation | — |
| Disk, network | Not verified from implementation | — |

All components (API, console, PostgreSQL, kind node) share one host. Interference between
them was not measured.

## 2. Software layout

```mermaid
flowchart TB
    subgraph Host [Host - macOS, Docker Engine 29.3.1]
        API[FastAPI API · Python 3.12 · port 8000]
        WEB[Next.js console · Node 24 · port 3000]
        PG[(postgres:17-alpine · 127.0.0.1:5432<br/>volume autoresilience-pgdata)]
        subgraph Node [kind node autoresilience-control-plane · K8s v1.37.0 · containerd 2.3.4 · iptables kube-proxy]
            M[monitoring: Prometheus 3.15.0 + KSM v2.20.0]
            L[litmus: chaos-operator 3.31.0]
            S[shop: frontend ×3, checkout ×2, cart-redis ×1, loadgen ×1]
            X[resilience-sandbox: fragile ×1]
        end
    end
    API -- kubeconfig context kind-autoresilience --> Node
    API -- http://localhost:9090 --> M
    WEB -- /api/backend rewrite --> API
    API --> PG
```

## 3. Cluster

| Property | Value |
|---|---|
| Name / context | `autoresilience` / `kind-autoresilience` |
| Nodes | 1 (`autoresilience-control-plane`, role control-plane, also schedules workloads) |
| Config | `infra/kind/cluster.yaml`: `extraPortMappings` containerPort 30090 → hostPort 9090 on 127.0.0.1 |
| Namespaces | `default`, `kube-node-lease`, `kube-public`, `kube-system`, `litmus`, `local-path-storage`, `monitoring`, `resilience-sandbox` (label `autoresilience.io/sandbox=true`), `shop` |
| System namespaces (forbidden as targets, hidden from Services) | kube-system, kube-public, kube-node-lease, local-path-storage, litmus, monitoring |

## 4. Applications (targets and instruments)

| Namespace / workload | Kind | Replicas | Image | Readiness probe | Liveness | Resources (req / limit) | Server metrics | Client load | Policy |
|---|---|---|---|---|---|---|---|---|---|
| shop/frontend | Deployment | 3 | nginx:1.27-alpine | HTTP `/` :80, every 10 s | no | 10m CPU, 16Mi / 64Mi | no | yes | default |
| shop/checkout | Deployment | 2 | podinfo 6.9.2 | HTTP `/readyz` :9898, every 10 s | yes | 10m, 16Mi / 64Mi | `http_requests_total` (:9797) | yes | default |
| shop/cart-redis | StatefulSet | 1 | redis:7-alpine | `redis-cli ping`, every 10 s | no | 10m, 16Mi / 64Mi | no | no | default (blocked: 1 replica) |
| shop/loadgen | Deployment | 1 | python:3.12.11-alpine3.22 | HTTP `/metrics` :9100 | no | 20m, 24Mi / 64Mi | (instrument) | — | (not a target in practice) |
| resilience-sandbox/fragile | Deployment | 1 | podinfo 6.9.2 | HTTP `/readyz` :9898, **`initialDelaySeconds: 10`**, period 1 s | yes | 10m, 16Mi / 64Mi | `http_requests_total` (:9797) | yes | sandbox |

- **Services** (ClusterIP): `frontend:80→80`, `checkout:80→9898`, `cart-redis:6379`, `fragile:80→9898`.
- **Termination grace period:** 30 s (default) for all. **Strategy:** RollingUpdate.
- **Labels and selectors:** `app=<name>` for every workload.
- **Pod name patterns** used by AutoResilience queries: Deployment `<name>-[a-z0-9]+-[a-z0-9]{5}`, StatefulSet `<name>-[0-9]+`.

**Why `fragile` exists** (`infra/sample-app/sandbox.yaml` comment and commit `a0482fa`):
without a start-up delay, podinfo is Ready in about 0.5–1 s, so a single-replica deletion
caused no client-visible failures (B2/B1). The 10 s readiness delay **models** a realistic
warm-up and makes outages reproducible. It is an artificial, controlled factor, not an
application property.

## 5. Policies

See [06](06-safety-framework.md) §2. In summary:
- `default`: max 300 s, max 1 affected replica, min 1 healthy replica after the fault.
- `sandbox` (`resilience-sandbox` only): min 0 healthy replicas.

Consequences for experiments (inference from the policy values):

| Target | Allowed? |
|---|---|
| fragile | yes (sandbox) |
| checkout (2 replicas) | yes |
| frontend (3 replicas) | yes |
| cart-redis (1 replica, default policy) | **blocked** by `min_healthy_replicas_after_fault` |
| loadgen (1 replica) | blocked by the same check |

## 6. Prometheus

| Setting | Value |
|---|---|
| Chart / values | `prometheus-community/prometheus` 29.35.0 / `monitoring/prometheus/values.yaml` |
| Components | server, kube-state-metrics; **disabled:** Alertmanager, node-exporter, pushgateway |
| `scrape_interval` / `evaluation_interval` | 15 s / 15 s |
| Retention | 2 d; **no persistent volume** (`persistentVolume.enabled: false`) |
| Exposure | NodePort 30090 → `http://localhost:9090` |
| Scrape targets used | kube-state-metrics; pods annotated `prometheus.io/scrape: "true"` (checkout, fragile, loadgen) via the `kubernetes-pods` job |
| Resources | server 100m CPU, 256Mi request / 1Gi limit |

## 7. LitmusChaos

| Setting | Value |
|---|---|
| Chart / values | `litmuschaos/litmus-core` 3.31.1 / `chaos/litmus/values.yaml` (`pullPolicy: IfNotPresent`, exporter disabled) |
| Images | chaos-operator, chaos-runner, go-runner 3.31.0 (pre-pulled into the node with `crictl`) |
| Experiment | `chaos/templates/pod-delete.yaml` (vetted `pod-delete` ChaosExperiment, go-runner 3.31.0), applied to `shop` and `resilience-sandbox` |
| ServiceAccount | `autoresilience-chaos` with a namespace-scoped Role ([06](06-safety-framework.md) §6) |
| Probes | none configured |
| Observed latency | engine creation → replacement pod creation ≈ 13–14 s (B1, six engines) |

## 8. AutoResilience configuration

`apps/api/app/core/config.py`; env vars or `apps/api/.env` (template `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/autoresilience` | Database (provided by `scripts/dev-db.sh`) |
| `PROMETHEUS_URL` / `PROMETHEUS_TIMEOUT_SECONDS` | `http://localhost:9090` / 5 | Metrics |
| `KUBE_CONTEXT` / `KUBE_REQUEST_TIMEOUT_SECONDS` | current context / 5 | Cluster (`kind-autoresilience`) |
| `BASELINE_WINDOW_SECONDS` | 300 | Baseline window |
| `CHAOS_START_TIMEOUT_SECONDS` / `CHAOS_POLL_INTERVAL_SECONDS` | 120 / 2 | Injection |
| `OBSERVATION_GRACE_SECONDS` | 180 | Litmus deadline beyond the duration |
| `RECOVERY_TIMEOUT_SECONDS` | 300 | Recovery deadline after Litmus finishes |
| `RECOVERY_STABLE_SAMPLES` / `RECOVERY_MAX_SAMPLE_GAP_SECONDS` / `RECOVERY_ERROR_RATIO_TOLERANCE` | 4 / 40 / 0.01 | Recovery rule |
| `ORCHESTRATOR_ENABLED` / `ORCHESTRATOR_INTERVAL_SECONDS` | true / 5 | Reconciler |
| `BASELINE_TIMEOUT_SECONDS` / `ORCHESTRATION_MAX_SECONDS` / `CLEANUP_GRACE_SECONDS` | 180 / 1800 / 120 | Orchestration deadlines |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | Defined but unused |
| `AUTORESILIENCE_API_URL` (web, build time) | `http://localhost:8000` | Proxy target baked into the Next.js build |

## 9. Database

| Item | Value |
|---|---|
| Engine | PostgreSQL 17 (`postgres:17-alpine`), Docker container `autoresilience-postgres`, `127.0.0.1:5432`, volume `autoresilience-pgdata` |
| Schema | one table `experiments`; Alembic head `08697f19aec0` |
| State at audit | **0 experiments** |

## 10. Reproducible setup

```bash
# Prerequisites: Docker (running), kind, kubectl, helm, uv, Node 24
./scripts/dev-cluster.sh                 # kind + sample apps + Prometheus + Litmus + chaos prerequisites (idempotent)
./scripts/dev-db.sh                      # PostgreSQL + alembic upgrade head (idempotent)

cd apps/api && uv sync --frozen
KUBE_CONTEXT=kind-autoresilience uv run fastapi dev app/main.py     # API on :8000, reconciler on

cd apps/web && npm ci
AUTORESILIENCE_API_URL=http://localhost:8000 npm run build && npm run start   # or: npm run dev
# Console http://localhost:3000; readiness: curl localhost:8000/ready
```

Health checks before an experiment block:
1. `curl localhost:8000/ready` returns `ready`.
2. `kubectl --context kind-autoresilience get deploy,sts -A` shows every workload at full replicas.
3. `curl localhost:9090/-/ready`.
4. The load generator's series exist (`loadgen_requests_total`).
5. **Wait at least 1 min after a Prometheus restart**, because baselines need ≥ 4 samples (`DEVELOPMENT.md`).

## 11. Environmental confounders

| Confounder | Note |
|---|---|
| Single node | No scheduling across nodes; the replacement is always on the same node and its image is cached |
| Image cache | Images are pre-pulled, so replacement start-up excludes image pulls |
| Shared host | API, console, DB and cluster compete for host CPU |
| kube-proxy iptables | Endpoint propagation behaviour affects client outage (documented explanations in `chaos/policies/safety-policy.md`) |
| Pre-existing orphan ChaosEngines | Six completed engines in `resilience-sandbox`; inert, but should be deleted before a clean campaign (manual decision) |

---

## Related documents
[06-safety-framework](06-safety-framework.md) · [11-technology-stack](11-technology-stack.md) · [13-experimental-methodology](13-experimental-methodology.md) · [appendix/kubernetes-topology](appendix/kubernetes-topology.md) · [appendix/environment-versions](appendix/environment-versions.md)

## Missing information
- The host hardware model and the Docker resource allocation as configured (only the node capacity is known).
- No persistent Prometheus storage, so campaign telemetry must be exported.

## Open questions
- Should a campaign run on a dedicated machine, or with a fixed Docker resource allocation recorded in the paper?
