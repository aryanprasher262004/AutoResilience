# Recordings

Sanitized exports of real experiments (`<recording_id>.json`), validated in CI and replayed by
the public playground. `rec-*`: COMPLETED runs; `val-*`: safety-rejected experiments. Never add
test, sample or hand-written data here.

| File | Run | Evidence |
|---|---|---|
| `rec-9b735e4857856f50.json` | `shop/checkout` (2 replicas), pod-delete GRACEFUL, 60 s | development run, 2026-10-17 |
| `rec-fae3cb64e8c70d88.json` | `resilience-sandbox/fragile` (1 replica), pod-delete FORCE, 60 s | development run, 2026-10-17 |
| `val-f6a5dd497e8fae25.json` | `shop/cart-redis` (1 replica), refused: `min_healthy_replicas_after_fault` | development run, 2026-10-17 |

Contract and export runbook: [`docs/recordings.md`](../docs/recordings.md).
