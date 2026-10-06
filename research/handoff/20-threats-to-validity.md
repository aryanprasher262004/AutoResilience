# 20 · Threats to Validity

| | |
|---|---|
| **Purpose** | A complete catalogue of threats, separated into internal, external, construct, conclusion, engineering, measurement and infrastructure, each with mitigation and residual risk. |
| **Source of truth** | Implementation, environment and current evidence ([12](12-experimental-environment.md), [14](14-current-evidence.md), [15](15-observation-catalogue.md)). |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [13-experimental-methodology](13-experimental-methodology.md) (mitigations), [25-research-integrity](25-research-integrity.md) |

Mitigation status: `IMPL` (in the code) · `PROTO` (in the protocol, [13](13-experimental-methodology.md)) · `NONE`.

---

## 1. Internal validity

| ID | Threat | Evidence | Mitigation | Status | Residual risk |
|---|---|---|---|---|---|
| I-01 | Development runs used evolving builds | Commit brackets per record ([14](14-current-evidence.md)) | Single-commit campaign | PROTO | Low after the campaign |
| I-02 | Baseline contamination from recent faults inflates v3 | O-09 (7/13 runs) | ≥ 6 min spacing | PROTO | Low |
| I-03 | Order or time drift (host load, Prometheus state) | — | Interleave modes; randomise cells | PROTO | Medium |
| I-04 | Prometheus restarts reduce baseline samples | `MIN_SAMPLES = 4`; `CLAUDE.md` note | Warm-up wait; no restarts in a block | PROTO | Low |
| I-05 | Orphan objects from earlier runs | Six orphan engines | Clean before the campaign; record them | PROTO | Low |
| I-06 | Load generator restart resets counters | `INSUFFICIENT_DATA` handling | No loadgen changes in a block | IMPL+PROTO | Low |

## 2. External validity

| ID | Threat | Mitigation | Status | Residual risk |
|---|---|---|---|---|
| X-01 | Single-node kind cluster on a laptop; no multi-node scheduling, no image pulls | State explicitly; optional E7 | NONE | High |
| X-02 | Sample applications (podinfo, nginx, redis) are tiny and stateless or simple | State; E3 adds nginx | NONE | High |
| X-03 | The fragile warm-up is **modelled** (readiness delay), not real start-up work | State; E4 varies it | PROTO | Medium |
| X-04 | One fault type (pod-delete), one pod per run | Scope statement | NONE | High (scope) |
| X-05 | No production traffic patterns; one synthetic client at 10 req/s | State | NONE | High |
| X-06 | kube-proxy iptables mode; other data planes (IPVS, eBPF) may behave differently | State | NONE | Medium |

## 3. Construct validity

| ID | Threat | Evidence | Mitigation | Status |
|---|---|---|---|---|
| C-01 | "Resilience" is operationalised as a composite of author-chosen weights and thresholds | [09](09-scoring-methodology.md) | Present as an explainable instrument; V1 and E4 sensitivity | PROTO (partial) |
| C-02 | TTR measures replacement start-up only (it excludes deletion latency and client reconvergence) | [08](08-recovery-framework.md) §2 | Report client outage alongside | IMPL |
| C-03 | `request_failures` and `client_outage` overlap (same outage counted twice) | v3 doc limitation | State; consider in discussion | NONE |
| C-04 | The Litmus verdict is uninformative without probes | O-10 | State; analyse without the component | NONE |
| C-05 | The failure ratio is diluted by the growing observation window | v2 doc limitation | Report absolute failures too | PROTO |
| C-06 | The recovery decision ignores client evidence (COMPLETED while clients still fail is possible in principle) | [07](07-evidence-framework.md) §5 | Discuss | NONE |

## 4. Conclusion validity

| ID | Threat | Mitigation | Status |
|---|---|---|---|
| S-01 | Small n per cell (5–10) | Non-parametric summaries; avoid over-claiming; consider more repetitions | PROTO |
| S-02 | Current evidence is pre-experimental (B-level) | Do not use it for results ([25](25-research-integrity.md)) | PROTO |
| S-03 | Mode attribution unknown for most development runs | Do not infer mode effects from B1 | PROTO |
| S-04 | Multiple comparisons across cells | Report effect sizes and CIs; limit tests to pre-specified hypotheses | PROTO |

## 5. Engineering threats

| ID | Threat | Evidence | Status |
|---|---|---|---|
| E-01 | Single API process assumed (in-memory locks) | `docs/orchestration.md` | NONE (documented) |
| E-02 | The state-machine edge UNKNOWN → ABORTED is unreachable through the API | [08](08-recovery-framework.md) §5 | NONE (documentation inconsistency) |
| E-03 | The API runs with the developer kubeconfig (admin); read-only and ownership guarantees are code-level, not RBAC-enforced | [06](06-safety-framework.md) §6 | NONE |
| E-04 | No authentication or authorization | code search | NONE |
| E-05 | CI actions pinned to versions that GitHub flags as Node 20-based (deprecation notice in the first run) | [11](11-technology-stack.md) §6 | NONE (CI itself passes) |
| E-06 | The OpenAPI contract documents only 200/422 for experiment endpoints, while the API also returns 404/409/503 | [appendix/api-overview](appendix/api-overview.md) | NONE |
| E-07 | Stale documentation (`queries.md` and the v2 doc list two load-generator targets; root `README.md` scope and links) | [10](10-implementation.md) | NONE |

## 6. Measurement threats

| ID | Threat | Evidence | Mitigation | Status |
|---|---|---|---|---|
| M-01 | 15 s scrape interval misses sub-interval dips | O-03 | Client-side primary measures | IMPL |
| M-02 | Sequential client: timeouts cap failure counts during outages | v2 doc | Outage duration from counters (v3) | IMPL |
| M-03 | Outage resolution = request interval (0.1 s), up to 1 s during timeouts | loadgen doc | State | NONE |
| M-04 | Pod timestamps have 1 s resolution | recovery doc | State | NONE |
| M-05 | Client measurement not calibrated against ground truth | O-02 (consistency only) | C1 | PROTO |
| M-06 | The post-hoc telemetry windows (B1) differ from the system's observation windows | [14](14-current-evidence.md) §4 | Level A uses system windows | PROTO |

## 7. Infrastructure threats

| ID | Threat | Status |
|---|---|---|
| N-01 | Ephemeral Prometheus (2 d retention, no PV): raw telemetry is lost on restart | PROTO (export per run) |
| N-02 | Temporary databases caused the total loss of development records | IMPL (`dev-db.sh` persistent volume) + PROTO (exports) |
| N-03 | Shared host resources (API, console, DB, cluster on one machine) | NONE (record the resource settings) |
| N-04 | Floating image tags (`redis:7-alpine`, `nginx:1.27-alpine`) can change between campaigns | PROTO (record image digests) |
| N-05 | External chart repositories (Helm) could change pinned charts' dependencies | Low (charts pinned by version) |

---

## Related documents
[13-experimental-methodology](13-experimental-methodology.md) · [19-discussion-framework](19-discussion-framework.md) · [21-future-work](21-future-work.md) · [25-research-integrity](25-research-integrity.md)

## Missing information
- Quantified host interference.
- Image digests of the current deployment (`kubectl get pods -o jsonpath='{..imageID}'` should be recorded at campaign time).

## Open questions
- Which threats does the venue expect in the main text versus an appendix? Recommended: X-01, X-03, C-01, M-01 and S-01 in the main text.
