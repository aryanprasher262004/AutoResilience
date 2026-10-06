# Health and readiness

Implementation: `apps/api/app/services/readiness.py`, routes `app/api/routes/health.py`
and `app/api/routes/ready.py`; console indicator `apps/web/src/components/shell/api-status.tsx`.

## Concept: `/health` vs `/ready`

| | `GET /health` | `GET /ready` |
|---|---|---|
| Answers | is the API process up? | can the API serve normal operations now? |
| Touches | nothing | the database (`SELECT 1`, then `alembic_version`) |
| Success | `200 {"status": "ok"}` | `200`, `status: "ready"` |
| Failure | no answer at all | `503`, `status: "not_ready"` with a reason |

Use `/health` for liveness (restart the process if it stops answering) and `/ready` for
readiness (stop sending traffic, show the console as not ready). A `200` from `/health`
alone does not mean experiments, history or services will work.

## Contract: `GET /ready`

```json
{"status": "not_ready",
 "checks": [{"name": "database", "status": "fail", "reason": "database_unreachable",
             "detail": "Cannot connect to localhost:5432/autoresilience: connection failed: ..."}]}
```

`detail` names `host:port/database`, never credentials. Only the database is a readiness
dependency: Kubernetes and Prometheus are needed by some operations only, and those report
their errors per request (validation checks become `ERROR`, Services returns 503).

## Runbook: what a failed readiness check means

| `reason` | Meaning | Fix |
|---|---|---|
| `database_unreachable` | no connection to `DATABASE_URL` (stopped, wrong host/port, refused) | `./scripts/dev-db.sh`, or fix `DATABASE_URL` |
| `schema_missing` | connected, but no migration history (empty database) | `cd apps/api && uv run alembic upgrade head` |
| `schema_outdated` | migrated to a different revision than this API's migration head | `cd apps/api && uv run alembic upgrade head` (or deploy the matching API) |

While not ready, data endpoints answer `503` with the same cause in `detail` (see
`app/api/errors.py`), and `/health` keeps answering `200`.

## Console status (sidebar and Settings)

| Shown | When |
|---|---|
| ● API ready (green) | `/ready` returned `ready` |
| ● Database unavailable / not migrated / schema outdated (amber) | `/ready` returned `not_ready`; the reason picks the label, `detail` is the tooltip (and is shown on Settings) |
| ● API unreachable (red) | no API answer through the `/api/backend` proxy |

It polls every 15 s while ready and every 5 s otherwise; when it turns ready again, the
console refetches data that failed in the meantime.
