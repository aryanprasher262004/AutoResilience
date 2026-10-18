import type { Metadata } from "next";
import type { ReactNode } from "react";

import { TourLink } from "@/components/help/page-guides";
import { ShieldIcon } from "@/components/icons";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import type { ExperimentState } from "@/lib/api/types";
import { MODE_HELP, POD_DELETE_MODES } from "@/lib/experiment-options";
import { STATE_META } from "@/lib/experiment-state";
import { CHECK_HELP, PHASE_GUIDE, SUPPORTED_FAULT } from "@/lib/guidance";
import { docsUrl } from "@/lib/runtime";

export const metadata: Metadata = { title: "How it works" };

const PHASES: ExperimentState[] = ["CREATED", "VALIDATING", "BASELINING", "INJECTING", "OBSERVING", "RECOVERING"];

// Methodology v3 weights (WeightsV3 in apps/api; docs/scoring/resilience-score-v3.md).
const SCORE_V3: [string, number][] = [
  ["Recovery time", 35],
  ["Request failures", 30],
  ["Client outage", 15],
  ["Restarts", 10],
  ["Litmus verdict", 10],
];

function Section({ id, title, description, children }: { id: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-20">
      <Card>
        <CardHeader title={<span id={`${id}-title`}>{title}</span>} description={description} />
        {children}
      </Card>
    </section>
  );
}

export default function HowItWorksPage() {
  return (
    <>
      <PageHeader
        title="How it works"
        description="What happens between Check safety and the score, and what each phase records."
        actions={<TourLink page="overview" label="Take the Overview tour" />}
      />
      <div className="grid gap-4">
        <Section id="lifecycle" title="The lifecycle" description="Each phase stores its evidence before the next begins">
          <ol className="divide-y divide-line">
            {PHASES.map((state, i) => {
              const guide = PHASE_GUIDE[state];
              return (
                <li key={state} className="grid gap-2 px-4 py-3 md:grid-cols-[11rem_1fr_1fr]">
                  <p className="flex items-center gap-2 text-sm text-fg">
                    <span className="flex size-5 items-center justify-center rounded-full bg-accent/15 font-mono text-2xs text-accent">
                      {i + 1}
                    </span>
                    {STATE_META[state].label}
                  </p>
                  <p className="text-xs leading-relaxed text-muted">{guide?.doing}</p>
                  <p className="text-xs leading-relaxed text-faint">{guide?.next}</p>
                </li>
              );
            })}
          </ol>
        </Section>

        <Section id="safety" title="Safety model" description="Enforced by the engine; the console only shows the result">
          <CardBody className="grid gap-4 md:grid-cols-2">
            <div className="flex gap-3 text-sm leading-relaxed text-muted">
              <ShieldIcon className="mt-0.5 size-5 shrink-0 text-success" />
              <p>
                Limits come from a code-defined policy chosen only by the target namespace: <code className="font-mono text-fg">default</code>{" "}
                everywhere, and a <code className="font-mono text-fg">sandbox</code> policy for the reduced-redundancy namespace. A check
                that cannot be evaluated is an error, never a pass, and safety is checked again just before injection.
                The engine writes nothing to the cluster except the ChaosEngines it creates for its own runs.
              </p>
            </div>
            <dl className="grid gap-2 text-xs">
              {Object.entries(CHECK_HELP).map(([name, help]) => (
                <div key={name}>
                  <dt className="font-mono text-fg">{name}</dt>
                  <dd className="mt-0.5 text-muted">{help}</dd>
                </div>
              ))}
            </dl>
          </CardBody>
        </Section>

        <div className="grid gap-4 lg:grid-cols-2">
          <Section id="faults" title="Supported fault">
            <CardBody className="grid gap-3 text-sm text-muted">
              <p>
                <span className="font-mono text-fg">{SUPPORTED_FAULT.type}</span>: {SUPPORTED_FAULT.summary}
              </p>
              <ul className="grid gap-2">
                {POD_DELETE_MODES.map((mode) => (
                  <li key={mode} className="text-xs">
                    <span className="font-mono text-fg">{mode}</span> · {MODE_HELP[mode]}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-faint">{SUPPORTED_FAULT.unsupported}</p>
            </CardBody>
          </Section>

          <Section id="score" title="Resilience Score" description="Methodology v3, computed only from stored evidence">
            <CardBody className="grid gap-3">
              <dl className="grid gap-2.5">
                {SCORE_V3.map(([name, weight]) => (
                  <div key={name}>
                    <div className="flex justify-between text-xs">
                      <dt className="text-muted">{name}</dt>
                      <dd className="font-mono text-fg">{weight}</dd>
                    </div>
                    <div aria-hidden className="mt-1 h-1 rounded-full bg-surface-3">
                      <div className="h-1 rounded-full bg-accent" style={{ width: `${weight}%` }} />
                    </div>
                  </div>
                ))}
              </dl>
              <p className="text-xs leading-relaxed text-muted">
                A run that did not recover is capped at 40. Platform problems are not scored. Components without data
                are excluded and the remaining weights re-normalised; every score records its version.{" "}
                <a href={docsUrl("docs/scoring/resilience-score-v3.md")} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                  Full methodology ↗<span className="sr-only"> (opens in a new tab)</span>
                </a>
              </p>
            </CardBody>
          </Section>
        </div>

        <Section id="outcomes" title="Outcomes" description="How a run ends">
          <dl className="divide-y divide-line">
            {(["COMPLETED", "UNKNOWN", "VALIDATION_FAILED", "INJECTION_FAILED", "ABORTED"] as ExperimentState[]).map((state) => (
              <div key={state} className="grid gap-1 px-4 py-2.5 sm:grid-cols-[11rem_1fr]">
                <dt className="text-sm text-fg">{STATE_META[state].label}</dt>
                <dd className="text-xs text-muted">{STATE_META[state].description}</dd>
              </div>
            ))}
          </dl>
        </Section>
      </div>
    </>
  );
}
