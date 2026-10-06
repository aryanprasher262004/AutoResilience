# Appendix · API Overview

| | |
|---|---|
| **Purpose** | A research-oriented summary of the HTTP API: operations, purpose, inputs and status codes as implemented. This is not full API documentation. |
| **Source of truth** | `apps/api/app/api/routes/*.py`, `apps/api/app/api/errors.py`, `apps/api/app/schemas/*.py`; `packages/contracts/openapi.json` (generated) at `92e33dd`. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [../05-system-workflows](../05-system-workflows.md), [experiment-json-schema](experiment-json-schema.md) |

The status codes come from the **code**. The generated OpenAPI file declares only 200/422 (or
201/202) for most operations; the 404, 409 and 503 responses listed below are real but
undeclared (see [../20-threats-to-validity](../20-threats-to-validity.md) E-06).

---

## Experiments

| Method | Path | Purpose | Input | Success | Errors |
|---|---|---|---|---|---|
| POST | `/experiments` | Create (state CREATED) | `ExperimentCreate`: `name` (1–200), `description?` (≤ 2000), `target{namespace (DNS label ≤ 63), kind: Deployment\|StatefulSet, name (DNS subdomain ≤ 253)}`, `fault_type`, `duration_seconds > 0`, `affected_replicas > 0`, `pod_delete_mode` (GRACEFUL default \| FORCE) | 201 | 422 |
| GET | `/experiments` | List all (full records) | — | 200 | — |
| GET | `/experiments/history` | Filtered, sorted, paged slim rows | `q` (≤ 200), `state[]`, `fault_type[]`, `namespace[]`, `sort` ∈ {created_at, updated_at, name, score}, `order` ∈ {asc, desc}, `limit` 1–100 (25), `offset` ≥ 0 | 200 | 422 |
| GET | `/experiments/{id}` | One experiment (all evidence) | — | 200 | 404, 422 (bad UUID) |
| GET | `/experiments/{id}/score` | Stored score; `?version=v1\|v2` recomputes (not persisted) | `version` matches `^v[0-9]+$` | 200 | 404 (no score yet), 422 (unknown version) |
| POST | `/experiments/{id}/validate` | CREATED → VALIDATING → BASELINING \| VALIDATION_FAILED | — | 200 | 404, 409 (wrong state or auto-driven) |
| POST | `/experiments/{id}/baseline` | Manual baseline (BASELINING → INJECTING if CAPTURED) | — | 200 | 404, 409 |
| POST | `/experiments/{id}/inject` | Manual injection (blocking poll) | — | 200 | 404, 409 |
| POST | `/experiments/{id}/observe` | Manual observation step | — | 200 | 404, 409 |
| POST | `/experiments/{id}/run` | Hand over to the orchestrator (idempotent) | — | 202 | 404, 409 |
| POST | `/experiments/{id}/abort` | Stop own engine; → ABORTED | `{reason: 1–500 chars}` | 200 | 404, 409 (terminal, incl. UNKNOWN), 422 |

## Aggregation and discovery

| Method | Path | Purpose | Success | Errors |
|---|---|---|---|---|
| GET | `/dashboard/summary` | Counts, current-version score statistics, recovery and outage distributions, score history, namespaces, recent | 200 | — |
| GET | `/services` | Deployments and StatefulSets outside system namespaces, joined with history | 200 | 503 (cluster unreachable) |
| GET | `/services/{namespace}/{kind}/{name}` | Live pod status, tested faults, score history, recent experiments | 200 | 404 (system namespace, or unknown and without history), 422 (bad kind) |

## Operability

| Method | Path | Purpose | Success | Errors |
|---|---|---|---|---|
| GET | `/health` | Process liveness (no I/O) | 200 `{"status":"ok"}` | — |
| GET | `/ready` | DB reachable and at the migration head | 200 `ready` | 503 `not_ready` + `reason` ∈ {database_unreachable, schema_missing, schema_outdated} |

## Cross-cutting errors

| Condition | Response |
|---|---|
| Database unreachable (`OperationalError`) | 503 `Database unavailable at host:port/db: … Start it with scripts/dev-db.sh or set DATABASE_URL.` |
| Schema missing (`UndefinedTable`) | 503 with the migration command |
| Any other unhandled error | 500 |

## Placeholders (not implemented)

`routes/safety.py` (intended `GET /api/v1/safety-policy`), `routes/coverage.py` (intended
coverage endpoints).

---

## Related documents
[../04-component-design](../04-component-design.md) · [../05-system-workflows](../05-system-workflows.md) · [experiment-json-schema](experiment-json-schema.md)

## Missing information
- 404, 409 and 503 responses are not declared in the OpenAPI contract.

## Open questions
- None.
