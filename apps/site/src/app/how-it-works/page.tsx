import type { Metadata } from "next";

import { Container, PageHeader, Panel } from "@/components/primitives";
import { PHASES } from "@/lib/site";

export const metadata: Metadata = { title: "How It Works" };

const details: Record<(typeof PHASES)[number]["id"], string[]> = {
  validate: [
    "The policy is chosen by the target namespace only; it cannot be picked through the API.",
    "Static checks: namespace allowed, duration ≤ 300 s, affected replicas within the limit.",
    "Cluster checks: the workload exists and enough Ready pods remain after the fault.",
    "Every check is PASSED, FAILED, ERROR or SKIPPED. Only all-PASSED continues.",
  ],
  baseline: [
    "A 300 s Prometheus window before the fault: available replicas and restarts (required).",
    "Request rate and server error ratio when the workload exposes them; otherwise marked unavailable.",
    "Client-side request outcomes and outage counters from the load generator, where it targets the workload.",
  ],
  inject: [
    "Safety is re-checked against the cluster immediately before injection.",
    "A LitmusChaos ChaosEngine named after the experiment deletes exactly the selected pods, once.",
    "The run moves on only when Litmus is running and the targeted pods are confirmed gone.",
  ],
  observe: [
    "Each step reads Litmus, Prometheus and Kubernetes once and stores what it saw.",
    "Replacement pod creation and Ready times, sampled availability, restarts and server errors.",
    "Client failures counted exactly from counter samples, plus outage duration and pattern.",
  ],
  recover: [
    "Recovered when replacements are Ready and availability holds for 4 consecutive samples without gaps.",
    "If the baseline had traffic, the error ratio must also return to baseline.",
    "COMPLETED needs a Litmus Pass. Otherwise UNKNOWN: platform, application or conflicting evidence.",
  ],
  score: [
    "v3 components: recovery time, request failures, client outage, restarts, Litmus verdict.",
    "Not-recovered runs are capped at 40; platform or conflicting outcomes are not scored at all.",
    "The stored score names its version; v1 and v2 can be recomputed from the same evidence.",
  ],
};

export default function HowItWorksPage() {
  return (
    <>
      <PageHeader eyebrow="How it works" title="From a configured fault to an auditable decision.">
        <p>
          A run moves through explicit states, CREATED → VALIDATING → BASELINING → INJECTING → OBSERVING →
          RECOVERING → COMPLETED or UNKNOWN, and every transition is backed by stored evidence.
        </p>
      </PageHeader>
      <Container className="py-16">
        <ol className="relative space-y-6 border-l border-line pl-6 sm:pl-10">
          {PHASES.map((phase, i) => (
            <li key={phase.id} className="reveal relative">
              <span
                aria-hidden
                className="absolute top-6 -left-[calc(1.5rem+5px)] size-2.5 rounded-full border-2 border-canvas bg-accent sm:-left-[calc(2.5rem+5px)]"
              />
              <Panel className="p-6">
                <p className="font-mono text-xs text-accent">
                  {String(i + 1).padStart(2, "0")} · {phase.name}
                </p>
                <h2 className="mt-2 text-lg font-medium">{phase.summary}</h2>
                <ul className="mt-4 space-y-2 text-sm leading-relaxed text-muted">
                  {details[phase.id].map((line) => (
                    <li key={line} className="flex gap-3">
                      <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-faint" />
                      {line}
                    </li>
                  ))}
                </ul>
              </Panel>
            </li>
          ))}
        </ol>

        <Panel className="reveal mt-12 p-6">
          <h2 className="font-medium">Where things run</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            The engine, its database and the console run on your machine and talk to a cluster you own. The
            engine API has no authentication, so it stays on your machine and is never exposed publicly. This
            website is static files: it has no backend and cannot reach an engine.
          </p>
        </Panel>
      </Container>
    </>
  );
}
