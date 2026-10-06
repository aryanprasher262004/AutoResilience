# 23 · Reference Collection Guide

| | |
|---|---|
| **Purpose** | The research areas that need literature, the questions each must answer, and where each is used in a paper. **No citations are given or invented here.** |
| **Source of truth** | Claims in this knowledge base marked "Requires literature validation"; the technologies used. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [02-research-context](02-research-context.md), [22-paper-writing-guide](22-paper-writing-guide.md) |

**Rule:** collect primary sources (peer-reviewed papers, official specifications or
documentation, and the books that define the terms). Record each source with the claim it
supports, and verify every quotation against the source.

---

| Area | Questions the literature must answer | Used in | Source types |
|---|---|---|---|
| **A. Chaos engineering foundations** | Origin and principles; steady-state hypothesis; blast-radius minimisation; production vs pre-production experimentation | Introduction, background | Seminal papers and books; industry reports |
| **B. Chaos engineering tools for Kubernetes** | Capabilities of LitmusChaos and comparable tools (fault catalogues, verdicts, probes, safety features, scheduling); how they report results | Related work, T-19 | Official documentation; tool papers; comparative studies |
| **C. Safety and guard-rails in fault injection** | Policy-based admission, blast-radius controls, automatic abort and halting conditions, approval workflows | RQ1 positioning | Papers on safe experimentation; vendor docs |
| **D. Observability and SLIs** | Black-box vs white-box monitoring; client-side vs server-side SLIs; synthetic probing; scrape-based sampling limits | RQ2 positioning, O-03 discussion | SRE literature; monitoring papers; Prometheus docs |
| **E. Kubernetes self-healing and pod lifecycle** | Pod termination sequence, grace periods, readiness and endpoint propagation, kube-proxy behaviour during termination | Explaining O-04, O-05, O-06; method | Kubernetes official documentation; KEPs; papers on Kubernetes availability |
| **F. Resilience metrics and scoring** | Existing resilience or availability metrics (MTTR, error budgets, availability ratios); composite indices; resilience scoring in microservices | Score positioning; C-01 | Dependability literature; microservice resilience papers |
| **G. Recovery measurement** | Definitions of time to recovery and time to detect; measuring recovery in orchestrated systems | TTR definition ([08](08-recovery-framework.md)) | Dependability and SRE literature |
| **H. Uncertainty and inconclusive test outcomes** | Treatment of flaky or inconclusive outcomes in testing and experimentation | UNKNOWN taxonomy | Software testing literature |
| **I. Microservice benchmarks and evaluation methodology** | Benchmark applications for resilience studies; experimental design for systems research; repetitions and statistics | Evaluation design, threats | Systems-evaluation methodology papers; benchmark suites |
| **J. Methodology versioning and reproducibility** | Reproducible measurement; versioned metrics; artefact evaluation | Score versioning discussion | Reproducibility literature |
| **K. Self-service / platform engineering** | Internal developer platforms; self-service operations tooling; UX for operations | Introduction (motivation) | Industry and academic sources |
| **L. Design science research** (if framing as design science) | Artefact design and evaluation methodology | Method framing (optional) | Methodology literature |

## Claims currently requiring literature validation

| Claim location | Claim |
|---|---|
| [02](02-research-context.md) §2 | All gap statements |
| [02](02-research-context.md) §6 | Novelty of C1–C4 |
| [15](15-observation-catalogue.md) O-03 | Any generalisation about scrape-based monitoring |
| [19](19-discussion-framework.md) | Positioning of interpretations relative to prior work |
| [20](20-threats-to-validity.md) X-06 | Behaviour of other kube-proxy data planes |

## Technology documentation to cite (official sources)

FastAPI, SQLAlchemy, Alembic, PostgreSQL, Next.js, React, TanStack Query, Kubernetes
(pod lifecycle, probes, kube-proxy), kind, Helm, Prometheus (scrape model, PromQL range
vectors, staleness), kube-state-metrics (pod created and ready timestamps), LitmusChaos
(ChaosEngine, ChaosResult, pod-delete, `FORCE`, probes), podinfo.

---

## Related documents
[02-research-context](02-research-context.md) · [22-paper-writing-guide](22-paper-writing-guide.md) · [18-required-tables](18-required-tables.md) T-19

## Missing information
- All references.

## Open questions
- Which citation style does the venue require?
