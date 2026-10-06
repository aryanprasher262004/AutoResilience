# Appendix · Environment Versions

| | |
|---|---|
| **Purpose** | A single flat list of every version relevant to reproduction, with its provenance. |
| **Source of truth** | Lockfiles, manifests, scripts and live observation on 2026-10-07. Detailed context: [../11-technology-stack](../11-technology-stack.md). |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [../11-technology-stack](../11-technology-stack.md), [../12-experimental-environment](../12-experimental-environment.md) |

P = pinned in the repository; O = observed in the local environment.

| Component | Version | P/O | Where |
|---|---|---|---|
| Repository commit | `92e33dd` | P | git |
| Database schema head | `08697f19aec0` | P | `alembic/versions` |
| Python | 3.12.13 (≥ 3.12; CI 3.12) | O/P | runtime, `pyproject.toml`, `ci.yml` |
| FastAPI | 0.141.1 | P | `uv.lock` |
| Starlette | 1.6.0 | P | `uv.lock` |
| Pydantic | 2.13.4 | P | `uv.lock` |
| pydantic-settings | 2.15.0 | P | `uv.lock` |
| SQLAlchemy | 2.0.52 | P | `uv.lock` |
| psycopg | 3.3.4 | P | `uv.lock` |
| Alembic | 1.19.1 | P | `uv.lock` |
| kubernetes (Python) | 36.0.3 | P | `uv.lock` |
| httpx | 0.28.1 | P | `uv.lock` |
| uvicorn | 0.52.3 | P | `uv.lock` |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | P | `uv.lock` |
| ruff / mypy | 0.16.3 / 2.3.1 | P | `uv.lock` |
| Node.js | 24.13.1 (CI 24) | O/P | runtime, `ci.yml` |
| TypeScript | 5.9.3 | P | `package-lock.json` |
| Next.js | 16.3.8 | P | `package-lock.json` |
| React / React DOM | 19.2.8 | P | `package-lock.json` |
| TanStack Query | 5.104.1 | P | `package-lock.json` |
| Tailwind CSS | 4.3.3 | P | `package-lock.json` |
| openapi-typescript | 7.13.0 | P | `package-lock.json` |
| ESLint | 9.39.5 | P | `package-lock.json` |
| Vitest / Vite / happy-dom | 4.1.11 / 8.3.3 / 20.14.5 | P | `package.json` |
| Testing Library react / dom / user-event / jest-dom | 16.3.3 / 10.4.2 / 14.6.7 / 7.0.1 | P | `package.json` |
| PostgreSQL | 17 (`postgres:17-alpine`) | P | `dev-db.sh`, `ci.yml` |
| Docker Engine | 29.3.1 | O | `docker version` |
| kind | v0.33.0 | O | `kind version` |
| Kubernetes (node image) | v1.37.0 (`kindest/node:v1.37.0`) | O | node |
| containerd | 2.3.4 | O | node info |
| kube-proxy mode | iptables | O | ConfigMap |
| kubectl client | v1.35.3 | O | `kubectl version` |
| Helm | v4.3.0 | O | `helm version` |
| Prometheus chart / app | 29.35.0 / v3.15.0 | P / O | `dev-cluster.sh` / buildinfo |
| prometheus-config-reloader | v0.94.1 | O | pod image |
| kube-state-metrics | v2.20.0 | O | pod image |
| litmus-core chart | 3.31.1 | P | `dev-cluster.sh` |
| chaos-operator / chaos-runner / go-runner | 3.31.0 | P | `dev-cluster.sh`, template |
| CoreDNS | v1.14.6 | O | pod image |
| podinfo | 6.9.2 | P | manifests |
| nginx | 1.27-alpine (floating patch) | P | `shop.yaml` |
| redis | 7-alpine (floating minor) | P | `shop.yaml` |
| python (loadgen) | 3.12.11-alpine3.22 | P | `shop.yaml` |
| actionlint (validation only) | 1.7.12 | O | Docker image |
| Host OS | macOS, Darwin 25.6.0, arm64 | O | environment |
| Node capacity | 10 CPU, 8,024,472 KiB | O | node status |

---

## Related documents
[../11-technology-stack](../11-technology-stack.md) · [../12-experimental-environment](../12-experimental-environment.md)

## Missing information
- Host hardware model; image digests.

## Open questions
- None.
