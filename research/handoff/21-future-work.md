# 21 · Future Work

| | |
|---|---|
| **Purpose** | Future work only: what is planned or desirable, clearly separated from what is implemented. |
| **Source of truth** | Placeholders (`# OWNER` / `# Intended` headers), empty directories, documented limitations, gaps found in this knowledge base. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [10-implementation](10-implementation.md) §6.3, [20-threats-to-validity](20-threats-to-validity.md) |

Everything below is **Level D**. Nothing here may be described as existing.

---

## 1. Research work (highest priority)

| Item | Current | Future | Linked |
|---|---|---|---|
| Controlled evaluation campaign | No Level A evidence | Execute E1–E4, S1, R1, C1, V1 | [16](16-final-experiment-matrix.md) |
| Literature review and positioning | none | Related-work comparison (T-19) | [23](23-reference-collection-guide.md) |
| Score calibration | Author-chosen weights and thresholds | Sensitivity analysis; expert or SLO-based calibration | C-01 |
| Baseline-contamination-aware scoring | v3 subtracts a contaminated baseline outage | A v4 that excludes baseline windows overlapping recent faults (a new version, per the versioning rule) | O-09 |
| Mode-effect study | n = 1 per mode | E1 with ≥ 10 per mode | O-06 |

## 2. Product and engineering work

| Item | Current implementation | Future implementation | Source |
|---|---|---|---|
| Live safety monitor | none; deadlines and manual abort only | Abort on live signals during INJECTING and OBSERVING (e.g. SLO breach, unexpected pod loss) | `services/safety/live_monitor.py` placeholder |
| More fault types | Enum: `pod-cpu-hog`, `pod-memory-hog`, `pod-network-latency`; rejected by validation | Vetted engine builders, per-fault policies and evidence | `domain/experiment.py` |
| Multi-pod blast radius | `max_affected_replicas = 1` | Policy-controlled larger radii with stronger cluster checks | `safety_policy.py` |
| Litmus probes | none | HTTP or command probes, so the verdict reflects target health | O-10 |
| Client evidence in the recovery decision | recovery uses K8s and server evidence only | An optional "client success restored" criterion (new rule version) | C-06 |
| Coverage analytics | placeholders | targets × fault types × experiments matrix | `services/coverage/*`, `routes/coverage.py` |
| Safety-policy API and persistence | code-defined only | read-only `GET /api/v1/safety-policy`; persisted, reviewed policies | `routes/safety.py`, `db/models/safety_policy.py` |
| Timeline service | events in `orchestration.events` (≤ 50) | dedicated phase-event recording | `services/orchestration/timeline.py` |
| Structured logging | placeholder | logging configuration | `core/logging.py` |
| Server-side reports | printable console view only | versioned report artefacts (PDF or JSON), stored with the experiment | [04](04-component-design.md) §14 |
| Alertmanager / Grafana integration | disabled or empty | alert correlation, dashboards | root `README.md` scope; `monitoring/*` |
| CI reliability gates | CI validates code only | run resilience experiments as a pipeline gate | root `README.md` scope |
| Multi-replica API | in-process locks | DB row locks (`SELECT … FOR UPDATE SKIP LOCKED`) | `docs/orchestration.md` |
| Least-privilege API identity | developer kubeconfig | dedicated ServiceAccount with read-only plus own-CR rights | E-03 |
| Authentication | none | user identity and audit trail | E-04 |
| In-cluster deployment | host processes | Helm chart | `infra/helm` empty |
| OpenAPI completeness | 200/422 only documented | declare 404/409/503 responses | E-06 |
| Statistical aggregation in the product | per-run score; dashboard mean/min/max | per-service distributions and confidence intervals | — |

## 3. Evaluation extensions

| Item | Description |
|---|---|
| E5–E7 | StatefulSet target, not-recovered path, multi-node cluster ([16](16-final-experiment-matrix.md) §6) |
| Real applications | A microservice benchmark application (Not verified from implementation that any is available in the repository) |
| User study | Usability of the self-service workflow |
| Production-like environment | Managed Kubernetes, real traffic |

---

## Related documents
[10-implementation](10-implementation.md) · [16-final-experiment-matrix](16-final-experiment-matrix.md) · [20-threats-to-validity](20-threats-to-validity.md) · [24-engineering-decisions](24-engineering-decisions.md)

## Missing information
- Prioritisation agreed with the supervisor.

## Open questions
- Which future-work items belong in the paper versus only in the dissertation?
