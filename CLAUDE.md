# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AutoResilience is a self-service resilience testing platform for Kubernetes: configure a controlled failure, validate safety, observe impact via Prometheus/Alertmanager, measure recovery, calculate an explainable Resilience Score, and produce evidence-backed reports. Target stack: LitmusChaos for failure injection, FastAPI orchestration/analysis, PostgreSQL for experiment history, Next.js/React UI.

**Current state:** the full backend lifecycle `CREATED → VALIDATING → BASELINING → INJECTING → OBSERVING → RECOVERING → COMPLETED | UNKNOWN` runs against the real kind cluster, driven automatically by an in-process reconciler (`POST /run`): safety validation, Prometheus baseline, a real LitmusChaos pod-delete, and evidence-based recovery detection, and an explainable Resilience Score (v3, using client-side evidence incl. measured outage duration). Frontend/CI are scaffold.
- `apps/api` implements: settings (`app/core/config.py`), SQLAlchemy 2 + psycopg 3 (`app/db/`), the 11-state experiment state machine with explicit transitions (`app/domain/state_machine.py`), and the `Experiment` model (target namespace/kind/name, fault type, duration, affected replicas, `validation_result` JSON) with Alembic migrations.
- Endpoints: `GET /health`, `POST /experiments`, `GET /experiments`, `GET /experiments/{id}`, `POST /experiments/{id}/validate`, `POST /experiments/{id}/baseline`, `POST /experiments/{id}/inject`, `POST /experiments/{id}/observe`, `GET /experiments/{id}/score[?version=v1]`, `POST /experiments/{id}/run`, `POST /experiments/{id}/abort`. Validate runs `CREATED → VALIDATING → BASELINING | VALIDATION_FAILED` (`services/orchestration/preflight.py`). Baseline (`services/orchestration/baseline.py`) captures a Prometheus baseline and moves `BASELINING → INJECTING` only if it is `CAPTURED`; a `FAILED` capture is persisted and the experiment stays `BASELINING` (retryable). Inject (`services/orchestration/injection.py`) re-checks the cluster, creates a pod-delete ChaosEngine and moves `INJECTING → OBSERVING` only once Litmus is running and the target pods are gone; otherwise `INJECTION_FAILED` (engine stopped). The call blocks ~15s on kind. Observe (`services/orchestration/observation.py`, `POST /experiments/{id}/observe`) advances one bounded step per call (clients poll): `OBSERVING → RECOVERING` when Litmus finishes (verdict + ChaosResult persisted), `RECOVERING → COMPLETED` when the recovery rule in `services/orchestration/recovery.py` holds and Litmus said Pass, else `UNKNOWN` with `reason_code` and `cause` (`platform` | `application` | `conflicting_evidence`). Evidence lives in `experiments.observation`. Wrong-state calls get 409.
- Orchestration: `services/orchestration/orchestrator.py` `Reconciler` runs in a background thread started by the FastAPI lifespan (`ORCHESTRATOR_ENABLED`, tests set it false and call `Reconciler.tick()` directly). `/run` marks a CREATED experiment `orchestration.mode="auto"`; each tick advances auto experiments one step via the existing lifecycle functions (`run_validation`/`complete_validation`, `run_baseline`, `start_injection`/`advance_injection`, `advance_observation`), enforces baseline/overall deadlines, and cleans up finished runs' own ChaosEngine/ChaosResult via `delete_owned` (label-verified). Manual step endpoints return 409 for auto runs. Single API process assumed (per-experiment in-memory locks). Details: `docs/orchestration.md`.
- Scoring: `services/scoring/resilience_score.py` is pure (stored evidence only, no I/O, no LLM) and runs in the same transaction as the final state; result in `experiments.score`. Platform/conflicting `UNKNOWN` → `NOT_SCORED`; application `UNKNOWN` → `SCORED_NOT_RECOVERED` (capped at 40). Current version `v3` (`CURRENT_VERSION`; v1/v2 recomputable via `?version=`); every stored score records its version and older versions are recomputable from stored evidence — never change an existing version's semantics, add a new one. Methodology: `docs/scoring/resilience-score-v{1,2,3}.md`, kept in sync with the `WeightsV*`/`Thresholds`/`OutageThresholds` dataclasses.
- Client-side evidence: `loadgen` (`infra/sample-app/loadgen/loadgen.py`, stdlib Python in a ConfigMap) exports `loadgen_requests_total{target_namespace,target_workload,outcome}` (`success|http_error|connection_error|timeout`) and client-observed outage metrics (`loadgen_outage_seconds_total`, `loadgen_outages_total`, last outage start/end gauges) for `shop/checkout`, `shop/frontend` and `resilience-sandbox/fragile`; baseline group `client` and `observation.impact.client` (exact counts from raw counter samples, plus `outage` with pattern NONE/CONTINUOUS/INTERMITTENT/INSUFFICIENT_DATA) use it. Targets without it are `UNAVAILABLE`, not failed.
- Baseline: availability + restarts (kube-state-metrics, required) and request/error rate (`http_requests_total{status}`, optional → `UNAVAILABLE` if not exposed). Queries and rules are documented in `monitoring/prometheus/queries.md`. `integrations/prometheus_client.py` is read-only (GET `/api/v1/query` only) and raises `PrometheusError` on any failure.
- Safety: `domain/safety_policy.py` holds code-defined policies selected **only** by target namespace (`POLICIES_BY_NAMESPACE` → `policy_for_namespace`, injected as a resolver via `get_policy_resolver`): `default` everywhere, `sandbox` (`min_healthy_replicas=0`, allowlisted to `resilience-sandbox` only). Never expose policy choice through the API. Validation results record `policy` + `policy_selection`; injection refuses if the resolved policy differs from the validated one. `services/safety/policy_evaluator.py` is pure: `evaluate_static` (namespace forbidden/allowlist, max duration, max affected replicas) and `evaluate_cluster` (workload exists, running+ready pods, ready pods − affected ≥ `min_healthy_replicas`). Every check has a status `PASSED | FAILED | ERROR | SKIPPED`; only all-`PASSED` reaches `BASELINING`. Cluster is queried only if static checks pass; Kubernetes errors become `ERROR`, never a pass. Result JSON: `{passed, static_checks, cluster_checks, policy}`.
- Chaos: `integrations/chaos_provider.py` (`LitmusChaosProvider`) is the only cluster writer; it only creates/stops its own `ar-<experiment id>` ChaosEngines, built from typed fields, pod-delete only. Guarantees are documented in `chaos/policies/safety-policy.md`. Only `pod-delete` passes validation (`SUPPORTED_FAULT_TYPES`). Experiments carry `pod_delete_mode` (`GRACEFUL` default | `FORCE`), persisted and mapped only to the vetted experiment's `FORCE` env.
- Kubernetes: `integrations/kubernetes_adapter.py` is **read-only** (only `read_*`/`list_*` calls; tests assert this). Returns `WorkloadStatus` or `None` (404), raises `ClusterUnavailableError` otherwise. Uses kubeconfig context `KUBE_CONTEXT`; injected via `get_kubernetes_adapter` (tests override it with `FakeKubernetes` in `tests/conftest.py`).
- Local cluster: `scripts/dev-cluster.sh` creates kind cluster `autoresilience` (`infra/kind/cluster.yaml`, maps Prometheus NodePort 30090 → `localhost:9090`), deploys the sample `shop` namespace (`infra/sample-app/shop.yaml`: `frontend` nginx ×3, `checkout` podinfo ×2 with request metrics, `cart-redis` StatefulSet ×1, `loadgen` client-side load generator for checkout and frontend) installs Prometheus (chart `prometheus-community/prometheus`, pinned in the script; values in `monitoring/prometheus/values.yaml`: server + kube-state-metrics only), deploys the reduced-redundancy sandbox (`infra/sample-app/sandbox.yaml`: namespace `resilience-sandbox`, single-replica podinfo `fragile`), and installs LitmusChaos (`litmuschaos/litmus-core`: operator + CRDs, values in `chaos/litmus/values.yaml`) plus the vendored `chaos/templates/pod-delete.yaml` ChaosExperiment and `chaos/rbac/pod-delete-rbac.yaml` ServiceAccount into each chaos namespace (`shop`, `resilience-sandbox`).
- Placeholders (2-line `# OWNER: … / # Intended: …`): `services/{analysis,coverage}`, `services/safety/live_monitor.py`, `orchestration/timeline.py`, `db/models/safety_policy.py`, `schemas/{coverage,safety}.py`, routes `targets/safety/coverage/reports`. Read the `Intended:` line for planned scope and respect the `OWNER:` tag.
- `apps/web`: default create-next-app home page plus placeholder `(dashboard)` routes; `package.json` lists deps (react-query, react-hook-form, recharts, msw) that aren't in `package-lock.json` yet.
- `monitoring/{alertmanager,grafana}`, `packages/contracts/`, `infra/{helm,namespaces}` contain only placeholders; `docs/` holds only `docs/scoring/`; `.github/workflows/` is empty.

The root `README.md` states docs should be split into **Concept** (what a term means), **Decision** (why an approach was chosen), **Runbook** (how to operate/debug), and **Contract** (expected data/API shape) — follow this taxonomy if asked to add documentation, and don't duplicate implementation detail that's obvious from code.

## Repo layout

- `apps/api` — FastAPI backend, managed with `uv` (Python >=3.12). Source under `apps/api/app/`, routers under `apps/api/app/api/routes/`.
- `apps/web` — Next.js 16 / React 19 frontend, App Router, Tailwind v4. Source under `apps/web/src/app/`.
- `apps/web/AGENTS.md` — auto-generated by `next dev` (regenerated on every dev server start); don't hand-edit, and re-commit it if it reappears as a diff. It warns that this Next.js version may have breaking changes vs. training data and to check `node_modules/next/dist/docs/` before relying on prior Next.js knowledge.

## Commands

### Local cluster
```bash
./scripts/dev-cluster.sh   # idempotent: kind cluster + sample shop app + Prometheus (needs Docker running, kind, kubectl, helm); also installs Litmus
kind delete cluster --name autoresilience
```
Run the API against it with `KUBE_CONTEXT=kind-autoresilience` (Prometheus defaults to `http://localhost:9090`). Port mappings only apply at cluster creation: after changing `infra/kind/cluster.yaml`, run `kind delete cluster --name autoresilience` first. Prometheus storage is ephemeral, so baselines fail with insufficient data for ~1 min after a Prometheus restart.

### API (`apps/api`)
```bash
cd apps/api
uv sync                    # install deps (Python >=3.12)
uv run alembic upgrade head     # apply migrations to DATABASE_URL
uv run alembic revision --autogenerate -m "..."   # new migration after model changes
uv run fastapi dev app/main.py   # run dev server (or: uv run uvicorn app.main:app --reload)
uv run pytest              # run tests
uv run pytest path/to/test.py::test_name   # run a single test
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy .              # type check
```
Dev/test/lint tooling (`pytest`, `pytest-asyncio`, `ruff`, `mypy`) is declared in the `dev` dependency group in `pyproject.toml`; `uv sync` installs it.

- Config comes from env vars or `apps/api/.env` (see `.env.example`). `DATABASE_URL` defaults to `postgresql+psycopg://postgres:postgres@localhost:5432/autoresilience`; Alembic reads it from settings, not from `alembic.ini`.
- New models must be imported in `app/db/models/__init__.py` so autogenerate sees them.
- Tests use in-memory SQLite via a `get_db` override in `tests/conftest.py` (no Postgres needed); `FakeKubernetes`, `FakePrometheus` (answers baseline queries by name) and `FakeChaos` (scripted Litmus statuses) replace the integrations; injection polling uses a no-sleep `FAST_WAIT`; `/observe` time is controlled through the `get_now` dependency (`Clock` fixture) and `FakePrometheus.healthy_recovery()` seeds observation data. Keep models portable (non-native enums, `sa.Uuid`). Unit tests live in `tests/unit/`, HTTP tests in `tests/api/`.

### Web (`apps/web`)
```bash
cd apps/web
npm install
npm run dev      # start Next.js dev server
npm run build
npm run start
npm run lint      # eslint
```
No test runner is configured yet.
