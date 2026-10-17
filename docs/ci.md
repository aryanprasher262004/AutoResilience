# Continuous integration

Workflow: `.github/workflows/ci.yml`. It validates only; nothing is deployed.

## When it runs

Every pull request, every push to `main`, and on demand (`workflow_dispatch`). A newer
run for the same branch cancels the older one.

## Jobs (run in parallel)

Seven jobs, each a separate check on the pull request:

| Job | What fails it | Same thing locally |
|---|---|---|
| Backend · ruff, mypy, pytest | lint errors, type errors, failing tests | `cd apps/api && uv sync --frozen && uv run ruff check . && uv run mypy . && uv run pytest` |
| Backend · migrations on PostgreSQL | a migration that does not apply, or models changed without a migration | `./scripts/dev-db.sh` (applies `alembic upgrade head`), then `cd apps/api && uv run alembic check` |
| Frontend · lint, typecheck, build | ESLint errors, TypeScript errors, a failing `next build` | `npm ci` (root), then `npm run lint`, `npm run typecheck`, `npm run build` with `--workspace web` |
| Frontend · tests | a failing Vitest test (`apps/web/src/**/*.test.tsx`, see `apps/web/README.md`) | `npm ci && npm test --workspace web` |
| Site · lint, typecheck, tests, static export | the same for `apps/site`, plus `scripts/check-static.mjs`: config is static-export only, no server code or network calls in `src/`, no engine address in `out/`, and each page has `lang`, a title, one `h1`, `main`, a skip link and the CSP | `npm ci`, then `lint`, `typecheck`, `test`, `build`, `check` with `--workspace site` |
| Recorded evidence · schema and recordings | `packages/contracts/recorded-experiment.schema.json` differs from the Pydantic model, or a file in `recordings/` fails validation or its hash ([recordings.md](recordings.md)) | `cd apps/api && uv run python -m app.tools.export_recording schema --check && uv run python -m app.tools.export_recording verify ../../recordings` |
| API contract in sync | anything under `packages/contracts/`, `apps/web/src/lib/api/schema.ts` or `apps/site/src/lib/recordings/schema.ts` differs from what the code generates | `./scripts/gen-api-contracts.sh && git diff --exit-code -- packages/contracts apps/web/src/lib/api/schema.ts apps/site/src/lib/recordings/schema.ts` |

Fixing a contract failure: run `scripts/gen-api-contracts.sh` and commit the generated files.

## Decision: what CI does not need

- **No cluster, Docker Desktop or LitmusChaos.** The API tests run on in-memory SQLite with
  fakes for Kubernetes, Prometheus and Litmus (`apps/api/tests/conftest.py`); the frontend
  tests stub `fetch` with contract-typed responses and need no running API. End-to-end
  runs against kind stay a local, manual verification.
- **One service container.** Only the migration job uses PostgreSQL (`postgres:17-alpine`,
  the image `scripts/dev-db.sh` uses), because Alembic migrations and `alembic check` need a
  real database.
- **Locked toolchains.** `uv sync --frozen` and `npm ci` install exactly `uv.lock` and
  the root `package-lock.json` (npm workspaces: `apps/web`, `apps/site`, `packages/ui`); Python 3.12 and Node 24 are pinned in the workflow's `env`.
- **No formatter gate.** CI runs `ruff check`, not `ruff format --check`:
  `app/api/routes/health.py` is intentionally left unformatted.

## Validating the workflow file

`docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest` (actionlint, with
shellcheck for the `run:` scripts).
