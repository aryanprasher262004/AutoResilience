#!/usr/bin/env bash
# Regenerate the shared API contract from the FastAPI app and the frontend types.
#   packages/contracts/openapi.json  <- apps/api (source of truth)
#   apps/web/src/lib/api/schema.ts   <- openapi-typescript
#   packages/contracts/recorded-experiment.schema.json <- app/schemas/recording.py
# Run after changing any API route or Pydantic schema; commit both files.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(
  cd "${ROOT}/apps/api"
  ORCHESTRATOR_ENABLED=false uv run --frozen python -c \
    "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2, sort_keys=True))" \
    > "${ROOT}/packages/contracts/openapi.json"
  uv run --frozen python -m app.tools.export_recording schema > /dev/null
)
npm --prefix "${ROOT}/apps/web" run --silent api:types
echo "contracts regenerated"
