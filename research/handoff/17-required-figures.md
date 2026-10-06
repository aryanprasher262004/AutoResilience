# 17 · Required Figures

| | |
|---|---|
| **Purpose** | The complete list of figures a paper or dissertation should contain, each with purpose, draft caption, inputs, generation method and status. |
| **Source of truth** | Diagrams in this knowledge base (Mermaid); `research/experiment-results.*` (current); campaign exports (future). |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [03-system-architecture](03-system-architecture.md), [08-recovery-framework](08-recovery-framework.md), [09-scoring-methodology](09-scoring-methodology.md), [16-final-experiment-matrix](16-final-experiment-matrix.md) |

**Status:** `DRAFTABLE NOW` (implementation figures; a Mermaid source exists here) ·
`NEEDS DATA` (requires Level A) · `ILLUSTRATIVE` (may use B1 data if labelled).

**Generation rules.**
- Diagrams: render the Mermaid sources (e.g. `mmdc` or mermaid.live), then restyle consistently for the venue.
- Data figures: generate with a committed script from the raw exports ([13](13-experimental-methodology.md) §8); never draw them by hand.
- One series needs no legend. Use one y-axis per chart. Reserve status colours (red, amber, green) for state meanings.

---

| ID | Figure | Purpose | Draft caption | Inputs | How to generate | Status |
|---|---|---|---|---|---|---|
| F-01 | High-level architecture | Orient the reader | "AutoResilience architecture: console, API, reconciler, read-only integrations and the single chaos writer, and the evaluation cluster." | [03](03-system-architecture.md) §1 | Mermaid → vector | DRAFTABLE NOW |
| F-02 | Deployment (evaluation setup) | Show exactly what ran where | "Evaluation deployment: host processes, PostgreSQL container and single-node kind cluster with monitoring, chaos and target namespaces." | [03](03-system-architecture.md) §2, [12](12-experimental-environment.md) §2 | Mermaid | DRAFTABLE NOW |
| F-03 | Data flow | Show evidence accumulation per phase | "Evidence produced and persisted by each lifecycle phase." | [03](03-system-architecture.md) §3, [07](07-evidence-framework.md) §2 | Mermaid | DRAFTABLE NOW |
| F-04 | Experiment state machine | Define the lifecycle formally | "Experiment states and transitions; UNKNOWN carries a reason code and cause." | [03](03-system-architecture.md) §8 | Mermaid `stateDiagram` | DRAFTABLE NOW |
| F-05 | End-to-end sequence | Show orchestration | "Sequence of an automatic run from configuration to report." | [03](03-system-architecture.md) §7, [05](05-system-workflows.md) | Mermaid `sequenceDiagram` | DRAFTABLE NOW |
| F-06 | Layered safety model | Explain RQ1 mechanisms | "Safety layers from input validation to owned-resource cleanup; live monitoring is future work." | [06](06-safety-framework.md) §1 | Mermaid | DRAFTABLE NOW |
| F-07 | Evidence-to-decision flow | Explain how sources combine | "How Litmus, Kubernetes, server and client evidence determine the final state and the score." | [07](07-evidence-framework.md) §5 | Mermaid | DRAFTABLE NOW |
| F-08 | Recovery rule timeline | Make TTR and stability concrete | "Recovery timeline: engine creation, deletion, replacement ready (TTR), stable samples, client outage." | [08](08-recovery-framework.md) §2 | Annotated timeline; B1 run `LIT-66d86b9a` | ILLUSTRATIVE (label "development run") |
| F-09 | Single-run evidence timeline | Show raw signals of one run | "Client failures per scrape interval, sampled availability and pod events for one fragile run." | Campaign export (E1); could illustrate with B1 | Script from raw samples | NEEDS DATA |
| F-10 | Score computation diagram | Explain v3 | "v3 components, normalization, weight re-normalization, cap and rating." | [09](09-scoring-methodology.md) §2–4 | Mermaid or table-figure | DRAFTABLE NOW |
| F-11 | Score evolution v1 → v3 | Design-science narrative | "Methodology evolution and the measurement problem each version addressed." | [09](09-scoring-methodology.md) §5 | Mermaid | DRAFTABLE NOW |
| F-12 | Outage, failures and TTR per cell | Main result (RQ2, RQ3) | "Client outage, failed requests and TTR per workload and mode (n per cell)." | E1–E3 | Box or strip plots from exports | NEEDS DATA |
| F-13 | Sampling vs continuous measurement | Explain O-03 | "15 s scrape samples can miss a sub-interval outage that client counters capture." | Schematic + one real run | Hand-designed schematic plus real samples | ILLUSTRATIVE |
| F-14 | Detection rate and calibration | RQ2 instrument results | "(a) Outage detection: sampled availability vs client; (b) measured vs commanded outage (C1)." | E1, E4, C1 | Bar with Wilson CIs; scatter with identity line | NEEDS DATA |
| F-15 | Score components per cell / version | RQ3 | "Mean contribution of each component to v3 per cell, and v1/v2/v3 for identical evidence." | E1–E4, V1 | Stacked bars (one per cell) | NEEDS DATA |
| F-16 | Delay ablation | RQ3 sensitivity | "Client outage and v3 score vs readiness delay (fragile, GRACEFUL)." | E4 | Line or point plot (two panels, one y-axis each) | NEEDS DATA |
| F-17 | Console: builder safety step | Show self-service and server-authoritative safety | "Builder safety step showing the server's static and cluster checks." | Screenshot from a campaign run | Screenshot (redact nothing needed; no secrets shown) | NEEDS DATA (new screenshot) |
| F-18 | Console: live room | Show live evidence | "Live experiment room during RECOVERING." | Campaign run | Screenshot | NEEDS DATA |
| F-19 | Console: report | Show the evidence report | "Printable report sections for a completed experiment." | Campaign run | Screenshot or print-to-PDF | NEEDS DATA |
| F-20 | Kubernetes topology | Environment | "Namespaces, workloads, replicas and policies of the evaluation cluster." | [appendix/kubernetes-topology](appendix/kubernetes-topology.md) | Mermaid | DRAFTABLE NOW |

## Minimum set by venue

| Venue | Figures |
|---|---|
| IEEE or ACM conference (≈ 8–10 pages) | F-01, F-04 (or F-05), F-07, F-12, F-13 or F-14, F-15 |
| Journal | the conference set + F-02, F-06, F-08, F-10, F-11, F-16, F-17–F-19 |
| Dissertation | all |
| Presentation | F-01, F-05, F-06, F-12, F-13, F-18 |

---

## Related documents
[18-required-tables](18-required-tables.md) · [16-final-experiment-matrix](16-final-experiment-matrix.md) · [22-paper-writing-guide](22-paper-writing-guide.md)

## Missing information
- No rendered figure assets exist in the repository.
- No campaign data exists for the NEEDS DATA figures.

## Open questions
- What figure style or template does the target venue require?
