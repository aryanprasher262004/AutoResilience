# Recorded experiments (contract)

A recording is a sanitized, self-verifying JSON copy of one **COMPLETED** experiment, for
replay without an engine (v0.2 architecture §8). Contract `autoresilience-recording/1`:

- Source of truth: `apps/api/app/schemas/recording.py` (Pydantic, strict, unknown fields
  forbidden).
- Generated JSON Schema: `packages/contracts/recorded-experiment.schema.json` (never edited by
  hand; `scripts/gen-api-contracts.sh` or `export_recording schema` regenerates it).
- Committed recordings: `recordings/<recording_id>.json`. None exist yet: they come only from
  real runs, never from test or sample data.

## Shape

| Key | Content |
|---|---|
| `schema` | `"autoresilience-recording/1"`. Any other value is rejected as unsupported. |
| `recording_id` | `rec-` + 16 hex chars, stable per experiment, not the experiment UUID. |
| `provenance` | `evidence_category` (`controlled_research` \| `development_run`, declared at export), `evidence_level` (`unclassified` \| `A`), `level_a_review`, `synthetic`, `captured_at` (COMPLETED time), `exported_at`, `engine_commit`, `exporter_version`, `score_version`, `environment`. |
| `experiment` | Target, fault, validation checks and policy snapshot, baseline values, injection times, Litmus verdict, recovery finding, impact (incl. client outage), Kubernetes view after recovery, lifecycle (`state_since` + state transitions) and the score with its version and breakdown. |
| `integrity` | `sha256` over the canonical document without `integrity` (`json-sorted-compact/1`: sorted keys, no whitespace, UTF-8, UTC timestamps). |

## Rules

- **Evidence level.** The exporter always writes `unclassified`. `A` is a manual review decision
  and is valid only with `controlled_research`, `synthetic: false` and a `level_a_review`
  (`reviewed_by`, `reviewed_at`), which changes the hash. P1 ships no promotion tool, so no
  recording can be Level A yet. Only Level A is publishable (D-6).
- **Allowlist.** Only fields in the model are exported. Dropped: experiment UUID, name and
  description, all free-text messages, engine names, Litmus pod names, kube context, errors.
  Pod names become `pod-1…n`; namespace/workload become `namespace-1`/`workload-1` unless the
  target is a shipped sample workload (`shop/{frontend,checkout,cart-redis}`,
  `resilience-sandbox/fragile`). Retained text is engine-generated (recovery rule, score
  explanation/reasons). Every string is scanned for UUIDs, IPs, URLs, emails, cluster hostnames
  and secret markers, and any original identifier found in the output aborts the export.
- **Refused exports.** Not COMPLETED; missing baseline/chaos/observation/score/timeline (manual
  runs have no timeline); validation not all-PASSED; policy, fault or replica mismatch;
  baseline not CAPTURED; Litmus verdict not Pass; timestamps out of causal order; unknown score
  version; a stored score that `score_experiment` cannot reproduce from the stored evidence.
- **Versioning.** A breaking change adds `autoresilience-recording/2`; files stay valid against
  their own version, like score versions.

## Runbook

```bash
cd apps/api
# Read-only transaction by explicit id; prints to stdout unless --out is given.
uv run python -m app.tools.export_recording export <experiment-id> \
  --evidence-category controlled_research \
  --environment "kind, single node, sample apps" \
  --engine-commit <sha of the API that ran it> \
  --out ../../recordings/<recording_id>.json
uv run python -m app.tools.export_recording verify            # all of recordings/
uv run python -m app.tools.export_recording schema --check    # schema drift
```

Exit codes: `0` ok, `1` verification failed, `3` database unavailable, `2` export refused (`refused: <CODE>: …`, codes
`NOT_FOUND | NOT_COMPLETED | MISSING_EVIDENCE | INCONSISTENT | UNSUPPORTED_SCORE_VERSION |
UNSAFE | INVALID`). Review every file before committing; CI (`docs/ci.md`) re-validates each one
and its hash.
