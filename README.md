# AutoResilience

A self-service resilience-testing platform for Kubernetes. The workflow:

1. Configure a controlled failure.
2. Let the server check it against safety policies and the live cluster.
3. Run it through LitmusChaos.
4. Watch the impact from the Kubernetes, server and client side.
5. Get an evidence-based recovery decision and an explainable **Resilience Score**, with a printable report.

```mermaid
flowchart LR
    U([You]) --> WEB[Web console<br/>Next.js :3000]
    WEB -- /api/backend/* --> API[FastAPI API :8000<br/>+ orchestrator]
    API --> DB[(PostgreSQL :5432)]
    subgraph Cluster [kind cluster autoresilience]
        LIT[LitmusChaos]
        PROM[(Prometheus :9090)]
        APPS[Sample workloads<br/>shop · resilience-sandbox]
        LG[Load generator] --> APPS
        LIT -- pod-delete --> APPS
    end
    API -- read-only Kubernetes access --> APPS
    API -- own ChaosEngines only --> LIT
    API -- PromQL --> PROM
```

## What it does

| Step | What happens |
|---|---|
| **Configure** | Pick a workload (discovered from the cluster, or typed in) and a fault: `pod-delete`, mode `GRACEFUL` or `FORCE`, duration, affected replicas. |
| **Safety check** | The server applies a namespace-bound policy: system namespaces forbidden, max 300 s, max 1 affected replica, ≥ 1 healthy replica must remain (the sandbox namespace allows 0). It also checks the live workload. Unsafe experiments are blocked before anything touches the cluster. |
| **Run** | A background orchestrator captures a 300 s Prometheus baseline, re-checks safety, creates a LitmusChaos pod-delete for exactly the selected pod(s), and confirms the deletion. |
| **Observe** | Kubernetes pod timestamps, sampled availability, server 5xx, and **client-side** failures and outage duration (from a built-in load generator). |
| **Decide** | **COMPLETED**: replacement Ready plus 4 stable samples, and Litmus Pass. **UNKNOWN**: with a reason code and a cause (`platform`, `application`, `conflicting_evidence`). Uncertain runs are never reported as successes. |
| **Score** | Resilience Score **v3** (0–100) with a per-component breakdown: recovery time, client outage, request failures, restarts, Litmus verdict. Older methodologies (v1, v2) can be recomputed from the same evidence. |
| **Report** | Live experiment room, history, per-service view, and a printable report. |

Only `pod-delete` is supported. Other fault types are rejected by validation.

## Repository layout

| Path | Contents |
|---|---|
| `apps/api` | FastAPI backend (Python 3.12, `uv`): lifecycle, safety, orchestration, evidence, scoring, tests |
| `apps/web` | Next.js 16 console (React 19, TanStack Query), tests (Vitest) |
| `infra/` | kind cluster config, sample workloads (`shop`, `resilience-sandbox`), load generator |
| `chaos/` | LitmusChaos values, the vetted `pod-delete` experiment, RBAC, safety contract |
| `monitoring/prometheus/` | Prometheus values and the PromQL contract |
| `scripts/` | `dev-cluster.sh`, `dev-db.sh`, `gen-api-contracts.sh` |
| `packages/contracts/openapi.json` | Generated API contract (frontend types are generated from it) |
| `docs/` | Methodology and runbooks (scoring v1–v3, orchestration, readiness, services, history, CI) |
| `research/` | Evidence audit, extracted experiment data, and the research knowledge base (`research/handoff/`) |

---

## 1. Prerequisites

| Tool | Version used | Needed for |
|---|---|---|
| Docker (Desktop or Engine), running | 29.x | kind cluster, PostgreSQL |
| [kind](https://kind.sigs.k8s.io/) | 0.33 | local Kubernetes |
| kubectl | 1.35+ | cluster access |
| Helm | 4.x (3.x should also work, but is not verified) | Prometheus and Litmus charts |
| [uv](https://docs.astral.sh/uv/) | 0.11+ | Python 3.12 environment for the API |
| Node.js | 24 | web console |
| curl, `shasum` | — | used by the setup script |

Allocate enough resources to Docker. The reference environment's kind node had 10 CPUs and
about 8 GB of memory.

Ports used on localhost: **3000** (console), **8000** (API), **5432** (PostgreSQL),
**9090** (Prometheus).

## 2. Setup from a fresh clone

```bash
git clone https://github.com/aryanprasher262004/AutoResilience.git
cd AutoResilience
```

### 2.1 Cluster, monitoring, chaos and sample apps

```bash
./scripts/dev-cluster.sh
```

The script is idempotent and safe to re-run. It:
1. Creates the kind cluster `autoresilience` (context `kind-autoresilience`).
2. Deploys the sample workloads:
   - `shop`: `frontend` ×3, `checkout` ×2, `cart-redis` ×1, `loadgen`;
   - `resilience-sandbox`: `fragile` ×1, with a 10 s modelled start-up delay.
3. Installs Prometheus (exposed on `localhost:9090`) and the LitmusChaos operator.
4. Pre-pulls the chaos images.
5. Installs the `pod-delete` experiment and a namespace-scoped ServiceAccount into `shop` and `resilience-sandbox`.

Wait about **1–2 minutes** after it finishes before the first experiment. Baselines need at
least 4 Prometheus samples.

### 2.2 Database

```bash
./scripts/dev-db.sh
```

This starts PostgreSQL 17 in Docker (`autoresilience-postgres`, data in the volume
`autoresilience-pgdata`) and applies the migrations. It matches the API's default
`DATABASE_URL`, so no configuration is needed.

### 2.3 API

```bash
cd apps/api
uv sync --frozen
KUBE_CONTEXT=kind-autoresilience uv run fastapi dev app/main.py     # http://localhost:8000
```

Check it:

```bash
curl localhost:8000/health   # {"status":"ok"}: the process is up
curl localhost:8000/ready    # {"status":"ready",...}: the database is reachable and migrated
```

The orchestrator runs inside the API process (`ORCHESTRATOR_ENABLED=true` by default). Keep
the API running while experiments are active. If it restarts, runs resume from the database.

### 2.4 Web console

```bash
cd apps/web
npm ci
npm run dev        # http://localhost:3000 (expects the API on :8000)
```

For a production build:

```bash
AUTORESILIENCE_API_URL=http://localhost:8000 npm run build && npm run start
```

The API address is fixed **at build time**. **Settings** shows the address the running build
actually uses. The sidebar indicator shows **API ready** (green), a **database** problem
(amber), or **API unreachable** (red).

## 3. Using the console

| Page | Use it to |
|---|---|
| **Overview** (`/`) | See outcome counts, score statistics, recovery and outage medians, and recent experiments |
| **New Experiment** (`/experiments/new`) | Run the builder: **Configure → Safety check → Review & start** |
| **Experiments** (`/experiments`) | Browse history: search, filter by outcome, fault or namespace, sort, page |
| **Experiment room** (`/experiments/<id>`) | Follow a run live (3 s refresh): lifecycle, fault → impact → recovery, metrics, events, raw evidence; abort |
| **Reports** (`/reports`, `/reports/<id>`) | Read the printable report of a finished experiment (Print / Save as PDF) |
| **Services** (`/services`) | See discovered Deployments and StatefulSets with health, replica counts, latest score and history; start an experiment on one |
| **Settings** | Check the API target and readiness |

### Your first experiment (about 2 minutes)

1. Open **Services** and pick **`resilience-sandbox/fragile`** (1 replica, the sandbox policy allows removing it), then click **New experiment**. Or open **New Experiment** and choose it in *Discovered workload*.
2. Enter a name. Keep `pod-delete`, `GRACEFUL`, duration `30`, affected replicas `1`.
3. **Check safety.** The server's checks appear. All should pass.
4. **Continue to review**, tick the confirmation box ("I understand this will delete 1 pod …"), then **Start experiment**.
5. The live room opens. Expect BASELINING (up to about 5 min of history is used; it completes immediately if Prometheus has the data), then INJECTING, OBSERVING, RECOVERING and **COMPLETED**, typically about 100 s after the start.
6. Open the **report**. For `fragile` you should see a client outage of several seconds, about 20 failed client requests, and a score breakdown explaining the points lost.

Try `shop/checkout` (2 replicas) for comparison: clients usually see no failures. Try
`kube-system/coredns` to see a run **blocked** by safety validation.

## 4. Running experiments through the API

Everything in the console is available over HTTP. The interactive docs are at
`http://localhost:8000/docs`.

```bash
API=http://localhost:8000

# 1. Create
ID=$(curl -s -X POST $API/experiments -H 'content-type: application/json' -d '{
  "name": "fragile graceful",
  "target": {"namespace": "resilience-sandbox", "kind": "Deployment", "name": "fragile"},
  "fault_type": "pod-delete",
  "pod_delete_mode": "GRACEFUL",
  "duration_seconds": 30,
  "affected_replicas": 1
}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

# 2. Safety check (optional: /run also validates)
curl -s -X POST $API/experiments/$ID/validate | python3 -m json.tool | head -40

# 3. Start the automatic lifecycle (202)
curl -s -X POST $API/experiments/$ID/run > /dev/null

# 4. Follow it
while :; do
  STATE=$(curl -s $API/experiments/$ID | python3 -c 'import sys,json; print(json.load(sys.stdin)["state"])')
  echo "$STATE"
  case $STATE in COMPLETED|UNKNOWN|ABORTED|VALIDATION_FAILED|INJECTION_FAILED) break;; esac
  sleep 3
done

# 5. Results
curl -s $API/experiments/$ID | python3 -m json.tool          # full evidence record
curl -s $API/experiments/$ID/score                           # stored v3 score
curl -s "$API/experiments/$ID/score?version=v1"              # recompute an older methodology

# Abort an active run (stops only this experiment's own ChaosEngine)
curl -s -X POST $API/experiments/$ID/abort -H 'content-type: application/json' -d '{"reason": "stopping the demo"}'
```

| Useful endpoint | Purpose |
|---|---|
| `GET /experiments/history?state=COMPLETED&namespace=shop&sort=score&order=desc` | Filtered, paged history |
| `GET /dashboard/summary` | Aggregate statistics |
| `GET /services`, `GET /services/{ns}/{kind}/{name}` | Discovered workloads and their history |

### Running a series of experiments (for evaluation)

For repeatable measurements, follow `research/handoff/13-experimental-methodology.md`:
- **Space runs on the same target at least 6 minutes apart.** The 300 s baseline must not contain the previous outage.
- Keep the code commit and cluster unchanged during a series.
- Export every result (`GET /experiments/{id}`, plus `?version=v1|v2` scores) and dump the database after each block. Prometheus keeps raw data for only 2 days and has no persistent storage.

The planned evaluation matrix is in `research/handoff/16-final-experiment-matrix.md`.

## 5. Safety model (summary)

| Policy | Applies to | Max duration | Max affected | Min healthy remaining |
|---|---|---|---|---|
| `default` | every namespace except the sandbox | 300 s | 1 | 1 |
| `sandbox` | `resilience-sandbox` only | 300 s | 1 | 0 |

- System namespaces are always refused: `kube-system`, `kube-public`, `kube-node-lease`, `local-path-storage`, `litmus`, `monitoring`.
- Policies are chosen **only** by namespace, in code. No API field can select or change one.
- Safety is re-checked right before injection.
- The API never modifies the cluster, except for creating, stopping and deleting its own `ar-<experiment id>` ChaosEngines.
- Details: `chaos/policies/safety-policy.md`, `research/handoff/06-safety-framework.md`.

## 6. Configuration

The API reads environment variables, or `apps/api/.env` (see `apps/api/.env.example`).

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/autoresilience` | Provided by `scripts/dev-db.sh` |
| `KUBE_CONTEXT` | current kubectl context | Use `kind-autoresilience` |
| `PROMETHEUS_URL` | `http://localhost:9090` | |
| `BASELINE_WINDOW_SECONDS` | 300 | |
| `OBSERVATION_GRACE_SECONDS` / `RECOVERY_TIMEOUT_SECONDS` | 180 / 300 | Deadlines leading to UNKNOWN |
| `ORCHESTRATOR_ENABLED` / `ORCHESTRATOR_INTERVAL_SECONDS` | true / 5 | |

The web console uses `AUTORESILIENCE_API_URL` (default `http://localhost:8000`), read at build
time. The full list is in `research/handoff/12-experimental-environment.md` §8.

## 7. Development and tests

```bash
# Backend
cd apps/api
uv run pytest          # 431 tests, in-memory SQLite + fakes (no cluster needed)
uv run ruff check .
uv run mypy .

# Frontend
cd apps/web
npm test               # 39 Vitest tests
npm run lint
npm run typecheck
npm run build

# After changing API routes or schemas: regenerate and commit the contract
./scripts/gen-api-contracts.sh
```

CI (`.github/workflows/ci.yml`) runs the same checks on every pull request and on pushes to
`main`: backend, migrations on PostgreSQL, frontend build, frontend tests, and contract drift.
See `docs/ci.md`.

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Sidebar says **Database unavailable**; pages show 503 | PostgreSQL is not running: `./scripts/dev-db.sh` |
| **Database not migrated / schema outdated** | `cd apps/api && uv run alembic upgrade head` |
| **API unreachable** | Start the API (§2.3). For a production web build, check the address shown in **Settings** (it is fixed at build time). |
| Experiment stuck in BASELINING, then UNKNOWN `BASELINE_TIMEOUT` | Prometheus restarted recently or is unreachable. Check `curl localhost:9090/-/ready`, wait 1–2 min, and retry. |
| INJECTION_FAILED | Read `chaos.failure_reason` in the experiment. Common causes: the target is no longer healthy, or the namespace lacks the chaos setup (re-run `./scripts/dev-cluster.sh`). |
| UNKNOWN `LITMUS_TIMEOUT` | Litmus did not finish within duration + 180 s. Check `kubectl -n litmus get pods`. |
| Services page shows 503 | The API cannot reach the cluster. Check `KUBE_CONTEXT` and `kubectl --context kind-autoresilience get nodes`. |
| Old `ar-*` ChaosEngines in the cluster | Engines from experiments missing from the database are never deleted automatically. Remove them manually after checking: `kubectl -n resilience-sandbox get chaosengines`. |

## 9. Teardown

```bash
kind delete cluster --name autoresilience
docker rm -f autoresilience-postgres
docker volume rm autoresilience-pgdata        # deletes all experiment history
```

## 10. Documentation

| Where | What |
|---|---|
| `docs/scoring/resilience-score-v3.md` (and v1, v2) | Score methodology |
| `docs/orchestration.md` | Lifecycle orchestration, abort, cleanup |
| `docs/readiness.md`, `docs/services.md`, `docs/history-and-reports.md`, `docs/ci.md` | Contracts and runbooks |
| `chaos/policies/safety-policy.md` | Chaos safety contract |
| `monitoring/prometheus/queries.md` | PromQL used for baseline and observation |
| `research/handoff/README.md` | Research knowledge base: architecture, methodology, evidence, experiment plan, paper guide |
| `DEVELOPMENT.md` | Developer guide (current state, commands) |

### Documentation rule

Every important behaviour must be documented as one of:

- **Concept:** what a term means.
- **Decision:** why the team chose an approach.
- **Runbook:** how to operate or debug it.
- **Contract:** what data or API shape is expected.

Do not duplicate implementation details that are already obvious from code.

## Limitations

- Only `pod-delete`, one pod per experiment.
- Single cluster.
- Evaluated on a local kind cluster with sample applications.
- No authentication.
- No automatic abort on live signals; abort is manual.
- The score's weights and thresholds are design choices, not calibrated.
- Alertmanager and Grafana integration are not implemented.

See `research/handoff/20-threats-to-validity.md` and `research/handoff/21-future-work.md`.
