# Experiment history and dashboard API

Implementation: `apps/api/app/services/analysis/history.py`, routes in
`apps/api/app/api/routes/reports.py`. `GET /experiments` (full records) is unchanged.

## Contract: `GET /experiments/history`

Slim rows (`ExperimentSummary`) for lists, filtered, sorted and paged in SQL.

| Parameter | Meaning |
|---|---|
| `q` | case-insensitive substring of name, workload name or namespace |
| `state`, `fault_type`, `namespace` | repeatable; values within one parameter are OR-ed, parameters are AND-ed |
| `sort` | `created_at` (default), `updated_at`, `name`, `score` (unscored rows last) |
| `order` | `desc` (default) or `asc` |
| `limit`, `offset` | 1–100 (default 25), ≥ 0; the response carries `total` for paging |

Row fields derived from evidence:
- `time_to_recovery_seconds`: only for `COMPLETED` runs.
- `client_outage_seconds`: only when the client outage measurement status is `OK`.
- `outcome_reason`: the first recorded of the observation result reason, the orchestration
  result reason, the chaos failure reason and the abort reason; else the failed validation
  check messages.
- `auto` / `has_baseline`: let the UI say "validated · not started" without the full record.

`/experiments/history` is registered before `/experiments/{experiment_id}` so it is not
parsed as an id.

## Contract: `GET /dashboard/summary`

| Field | Rule |
|---|---|
| `outcomes` | `active` = non-terminal (including drafts), `failed` = VALIDATION_FAILED + INJECTION_FAILED, `undetermined` = UNKNOWN |
| `scores` | **current methodology only** (`version`); `not_scored` and `other_versions` are counted, never averaged in |
| `recovery_time_seconds` | median/min/max over COMPLETED runs |
| `client_outage_seconds` | median/min/max over runs with an `OK` client outage measurement |
| `score_history` | current-version scored runs, ordered by `updated_at` |
| `namespaces` | per target namespace: runs, completed, last activity |
| `recent` | the 8 newest experiments, as history rows |

## Decision: aggregate on the server

The overview is computed from every experiment in one place, so numbers don't depend on how
many rows the browser loaded. Scores from different methodologies are never mixed: a v1 or v2
score stored on an older run is reported as `other_versions` instead of being averaged with
v3. The UI shows the score trend only from 3 scored runs, so a single result is not shown as a
trend.
