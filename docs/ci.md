# Continuous integration

Workflow: `.github/workflows/ci.yml`. It validates only; nothing is deployed.

## When it runs

Every pull request, every push to `main`, and on demand (`workflow_dispatch`). A newer
run for the same branch cancels the older one.

## Jobs (run in parallel)

| Job | What fails it | Same thing locally |
|---|---|---|
| Backend · ruff, mypy, pytest | lint errors, type errors, failing tests | `cd apps/api && uv sync --frozen && uv run ruff check . && uv run mypy . && uv run pytest` |
| Backend · migrations on PostgreSQL | a migration that does not apply, or models changed without a migration | `./scripts/dev-db.sh` (applies `alembic upgrade head`), then `cd apps/api && uv run alembic check` |
| Frontend · lint, typecheck, build | ESLint errors, TypeScript errors, a failing `next build` | `cd apps/web && npm ci && npm run lint && npm run typecheck && npm run build` |
| API contract in sync | `packages/contracts/openapi.json` or `apps/web/src/lib/api/schema.ts` differ from what the code generates | `./scripts/gen-api-contracts.sh && git diff --exit-code -- packages/contracts/openapi.json apps/web/src/lib/api/schema.ts` |

Fixing a contract failure: run `scripts/gen-api-contracts.sh` and commit both generated files.

## Decision: what CI does not need

- **No cluster, Docker Desktop or LitmusChaos.** The API tests run on in-memory SQLite with
  fakes for Kubernetes, Prometheus and Litmus (`apps/api/tests/conftest.py`). End-to-end
  runs against kind stay a local, manual verification.
- **One service container.** Only the migration job uses PostgreSQL (`postgres:17-alpine`,
  the image `scripts/dev-db.sh` uses), because Alembic migrations and `alembic check` need a
  real database.
- **Locked toolchains.** `uv sync --frozen` and `npm ci` install exactly `uv.lock` and
  `package-lock.json`; Python 3.12 and Node 24 are pinned in the workflow's `env`.
- **No formatter gate.** CI runs `ruff check`, not `ruff format --check`:
  `app/api/routes/health.py` is intentionally left unformatted.

## Validating the workflow file

`docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest` (actionlint, with
shellcheck for the `run:` scripts).
