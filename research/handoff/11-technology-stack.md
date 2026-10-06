# 11 · Technology Stack

| | |
|---|---|
| **Purpose** | Exact technology versions for languages, libraries, frameworks, infrastructure, tooling and CI. |
| **Source of truth** | `apps/api/uv.lock`, `apps/api/pyproject.toml`, `apps/web/package-lock.json`, `apps/web/package.json`, `scripts/dev-cluster.sh`, `scripts/dev-db.sh`, `.github/workflows/ci.yml`, live `kubectl`/`helm`/`docker` output and Prometheus `buildinfo` read on 2026-10-07. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [12-experimental-environment](12-experimental-environment.md), [appendix/environment-versions](appendix/environment-versions.md) |

"Pinned" means fixed by a lockfile, a chart version or an image tag in the repository. "Observed"
means read from the running local environment. Observed values can drift and are not
guaranteed by the repository.

---

## 1. Languages and runtimes

| Item | Version | Source |
|---|---|---|
| Python | 3.12.13 (observed); `requires-python >= 3.12`; CI pins 3.12 | `pyproject.toml`, `ci.yml`, `uv run python --version` |
| TypeScript | 5.9.3 | `package-lock.json` |
| Node.js | 24.13.1 (observed); CI pins 24 | `node --version`, `ci.yml` |
| SQL | PostgreSQL 17 (`postgres:17-alpine`) | `scripts/dev-db.sh`, `ci.yml` |
| Load generator | Python 3.12.11 stdlib (`python:3.12.11-alpine3.22`) | `shop.yaml` |

## 2. Backend libraries (pinned by `uv.lock`)

| Library | Version | Role |
|---|---|---|
| FastAPI | 0.141.1 | Web framework |
| Starlette | 1.6.0 | ASGI toolkit (via FastAPI) |
| Pydantic | 2.13.4 | Schemas, validation |
| pydantic-settings | 2.15.0 | `Settings` |
| SQLAlchemy | 2.0.52 | ORM |
| psycopg | 3.3.4 | PostgreSQL driver |
| Alembic | 1.19.1 | Migrations |
| kubernetes (Python client) | 36.0.3 | Kubernetes API |
| httpx | 0.28.1 | Prometheus HTTP |
| uvicorn | 0.52.3 | ASGI server |
| pytest | 9.1.1 | Tests |
| pytest-asyncio | 1.4.0 | Tests |
| ruff | 0.16.3 | Lint |
| mypy | 2.3.1 | Types |

## 3. Frontend libraries (pinned by `package-lock.json`)

| Library | Version | Role |
|---|---|---|
| Next.js | 16.3.8 | App Router framework |
| React / React DOM | 19.2.8 | UI |
| @tanstack/react-query | 5.104.1 | Data fetching, polling |
| Tailwind CSS | 4.3.3 | Styling |
| openapi-typescript | 7.13.0 | Types from the OpenAPI contract |
| ESLint / eslint-config-next | 9.39.5 / 16.3.8 | Lint |
| Vitest | 4.1.11 | Tests |
| Vite | 8.3.3 | Vitest peer |
| happy-dom | 20.14.5 | Test DOM |
| @testing-library/react / dom / user-event / jest-dom | 16.3.3 / 10.4.2 / 14.6.7 / 7.0.1 | Component tests |

## 4. Infrastructure

| Item | Version | Pinned or observed |
|---|---|---|
| kind | v0.33.0 | Observed (`kind version`) |
| Node image / Kubernetes | `kindest/node:v1.37.0` / v1.37.0 | Observed |
| containerd | 2.3.4 | Observed (node info) |
| Node OS | Debian GNU/Linux 13 | Observed |
| kube-proxy mode | iptables | Observed (kube-proxy ConfigMap) |
| kubectl (client) | v1.35.3 | Observed |
| Helm | v4.3.0 | Observed |
| Docker Engine | 29.3.1 | Observed |
| Prometheus | 3.15.0, chart `prometheus-community/prometheus` 29.35.0 | Chart pinned; app version observed |
| prometheus-config-reloader | v0.94.1 | Observed |
| kube-state-metrics | v2.20.0 | Observed |
| LitmusChaos | chart `litmuschaos/litmus-core` 3.31.1; chaos-operator, chaos-runner, go-runner 3.31.0 | Pinned (`dev-cluster.sh`, template image) |
| CoreDNS | v1.14.6 | Observed |
| Sample images | podinfo 6.9.2, nginx 1.27-alpine, redis 7-alpine, python 3.12.11-alpine3.22 | Pinned in manifests (`redis:7` and `nginx:1.27` are floating minor tags) |

## 5. Tooling

| Tool | Use |
|---|---|
| uv | Python environment and lock (`uv sync --frozen`) |
| npm | Node packages (`npm ci`) |
| Alembic | Migrations, `alembic check` drift detection |
| openapi-typescript | Frontend types |
| actionlint (Docker image, 1.7.12) | Workflow validation (local) |

## 6. CI (`.github/workflows/ci.yml`)

| Job | Steps | Service containers |
|---|---|---|
| Backend · ruff, mypy, pytest | `uv sync --frozen`, `ruff check`, `mypy`, `pytest` | none |
| Backend · migrations on PostgreSQL | `alembic upgrade head`, `alembic check` | `postgres:17-alpine` |
| Frontend · lint, typecheck, build | `npm ci`, `lint`, `typecheck`, `build` | none |
| Frontend · tests | `npm ci`, `npm test` | none |
| API contract in sync | regenerate the contract; `git diff --exit-code` | none |

Triggers: every pull request, pushes to `main`, `workflow_dispatch`. The workflow has
read-only permissions and per-ref concurrency. The first GitHub run passed: all 5 jobs green (run 37538740103, 2026-10-06T22:09Z, commit `995c66d`).

---

## Related documents
[10-implementation](10-implementation.md) · [12-experimental-environment](12-experimental-environment.md) · [appendix/environment-versions](appendix/environment-versions.md)

## Missing information
- The host OS version and hardware model are not recorded.

## Open questions
- Should the paper cite observed tool versions (kind, kubectl, Helm) or only the pinned ones? Recommended: cite both, labelled.
