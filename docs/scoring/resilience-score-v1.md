# Resilience Score v1

Implementation: `apps/api/app/services/scoring/resilience_score.py` (pure, deterministic, no LLM).
Persisted in `experiments.score`; served by `GET /experiments/{id}/score`.

## Concept

A 0–100 summary of how well a target withstood one fault, computed **only** from evidence the
lifecycle already stored: the baseline (`experiments.baseline`) and the observation record
(`experiments.observation`). Every point is traceable to a component with its raw measurement,
normalized score, weight, contribution and reason.

## Contract: when an experiment is scored

Scoring runs automatically in the same transaction that moves an experiment to `COMPLETED` or
`UNKNOWN`.

| Final state | `observation.result.cause` | Score status | Score |
|---|---|---|---|
| `COMPLETED` (Litmus Pass + recovery rule held) | — | `SCORED` | 0–100 |
| `UNKNOWN` | `application` (reliable data, target did not recover in time) | `SCORED_NOT_RECOVERED` | recovery component = 0, total **capped at 40** |
| `UNKNOWN` | `platform` (Litmus/Prometheus unreadable, errored, timed out, data gaps) | `NOT_SCORED` | none |
| `UNKNOWN` | `conflicting_evidence` (Litmus Fail but metrics show recovery) | `NOT_SCORED` | none |
| anything else | — | `NOT_SCORED` | none |

A platform failure says nothing about the target, so it never gets a number. A target that did
not recover gets a number but cannot look like a good run: it has a distinct status and the cap.

## Formula

```
score = 100 × Σ(weightᵢ × normalizedᵢ) / Σ(weightᵢ of applicable components)     (rounded to 0.1)
```

A component is `NOT_APPLICABLE` when its input was not measurable for this target. It is excluded
and the remaining weights re-normalize (`effective_weight`). This is recorded in the breakdown
and explanation, and it is never treated as a failure.

| Component | Weight | Raw measurement (stored evidence) | Normalized 0–1 |
|---|---:|---|---|
| `recovery_time` | 35 | `recovery.time_to_recovery_seconds` (replacement pod created → Ready) | 1 if ≤ 10 s; 0 if ≥ 120 s; linear in between. 0 if not recovered. |
| `availability` | 25 | `impact.min_available_replicas` vs baseline `desired_replicas` | min / desired, clamped to [0, 1] |
| `error_ratio` | 20 | `impact.errors_in_window / requests_in_window` vs baseline `error_ratio` | increase ≤ 0.001 → 1; ≥ 0.05 → 0; linear. `NOT_APPLICABLE` if the baseline had no request metrics or no traffic. 0 if the baseline had traffic but none was recorded during the fault. |
| `restarts` | 10 | `impact.restarts_in_window` | 1 − restarts / 2, floored at 0 (0 → 1, 1 → 0.5, ≥ 2 → 0) |
| `litmus_verdict` | 10 | `litmus.verdict` | Pass → 1, otherwise 0 |

**Rating bands:** ≥ 90 Excellent, ≥ 75 Good, ≥ 50 Fair, < 50 Poor.

Weights and thresholds live in the `Weights` and `Thresholds` dataclasses, and each score stores a
copy of them, so a stored score stays interpretable if v2 changes them.

## Decision: why these components and weights

- **Recovery time (35)** is the core resilience question and the most precise measurement we
  have (Kubernetes object timestamps, 1 s resolution). The thresholds reflect that a healthy
  Deployment replaces a pod in seconds, while needing 2 minutes or more is clearly slow.
- **Availability (25)** captures capacity lost beyond expectations.
- **Error ratio (20)** is the closest stored signal to user impact, where the target exposes it.
  It is measured relative to the baseline, so a target with a pre-existing error rate is not
  penalized for it.
- **Restarts (10)** capture collateral instability. Pod-delete should not cause container
  restarts.
- **Litmus verdict (10)** is the chaos tool's independent judgment. In `COMPLETED` runs it is
  always Pass, because completion requires it. It only differentiates application-`UNKNOWN`
  runs, which is why its weight is small.

A linear model with five transparent components was chosen over anything learned or
nonlinear, so the score can be checked by hand.

## Worked example (real run, kind, `shop/checkout` pod-delete, 30 s)

Evidence:
- Replacement pod created and Ready within the same second (`time_to_recovery_seconds = 0`).
- Minimum availability 2/2.
- 163 requests, 0 5xx (baseline 0).
- 0 restarts.
- Litmus Pass.

Result: every component normalized to 1.0, giving **100.0 / 100 (Excellent)**.

Hypothetical: the same run recovering in 65 s gives recovery = 0.5, so the contribution is 17.5
of 35 and the score is **82.5 (Good)**.

## Known limitations of v1

- **Availability** is the minimum over 15 s scrapes. On kind, podinfo replaces a pod in about
  1 s, so dips are usually invisible and this component is coarse.
- **Errors** are server-side (`http_requests_total`). Connections refused while a pod terminates
  are not counted, so client-perceived impact is under-measured.
- **Recovery time** measures replacement start-up only. It does not include client-perceived
  downtime or time to reconverge in load balancers.
- **Single run:** there is no statistical aggregation across repeated runs. A score describes one
  experiment, not a service.
