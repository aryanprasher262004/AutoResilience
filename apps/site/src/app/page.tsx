import Link from "next/link";

import {
  ButtonLink,
  Container,
  Eyebrow,
  Panel,
  SectionHeading,
  StatusBadge,
} from "@/components/primitives";
import { Topology } from "@/components/topology";
import { PHASES, SCORE_V3 } from "@/lib/site";

const problems = [
  {
    title: "Replica counts are not evidence",
    body: "“It has three replicas” says nothing about how long users saw errors while one was replaced.",
  },
  {
    title: "Unbounded chaos is just an outage",
    body: "Failure injection needs limits that are checked against the live cluster before anything is deleted.",
  },
  {
    title: "Pass or fail hides the story",
    body: "A verdict without timing, client impact and the reason behind it cannot be reviewed or compared.",
  },
];

const safety = [
  "System namespaces are never a target",
  "At most 300 seconds per fault",
  "At most one affected replica per run",
  "At least one healthy replica must remain (outside the sandbox namespace)",
  "The live workload is checked before injection",
  "A check that cannot be evaluated never passes",
];

export default function HomePage() {
  return (
    <>
      {/* Hero */}
      <section aria-labelledby="hero-title" className="relative overflow-hidden pt-36 pb-20 sm:pt-44">
        <div aria-hidden className="hero-grid absolute inset-0 -z-10" />
        <Container>
          <div className="flex flex-wrap items-center gap-3">
            <Eyebrow>Resilience testing for Kubernetes</Eyebrow>
            <StatusBadge status="planned">Pre-release</StatusBadge>
          </div>
          <h1
            id="hero-title"
            className="mt-5 max-w-4xl text-display font-semibold tracking-[-0.035em] text-balance"
          >
            Break one pod on purpose. <span className="text-muted">Get evidence of how your service recovers.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted text-pretty">
            AutoResilience checks a controlled failure against safety policy, captures a Prometheus baseline,
            deletes exactly the pods you chose through LitmusChaos, and measures recovery from Kubernetes,
            server and client evidence. Every run ends in a decision you can audit and an explainable
            Resilience Score.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <ButtonLink href="/playground" variant="primary">
              Try Playground
            </ButtonLink>
            <ButtonLink href="/download">Download</ButtonLink>
          </div>
          <p className="mt-4 text-sm text-faint">
            Not yet released. The playground opens once real recorded runs exist; today it runs from source.
          </p>

          <Panel className="mt-16 overflow-hidden p-4 sm:p-8">
            <div className="pan">
              <Topology />
            </div>
          </Panel>
        </Container>
      </section>

      {/* Problem */}
      <section aria-labelledby="problem" className="border-t border-line py-24">
        <Container>
          <SectionHeading id="problem" eyebrow="Why" title="Resilience is a claim until something fails.">
            Kubernetes restarts pods. Whether your users notice is a different question, and it only has an
            answer if you measure it.
          </SectionHeading>
          <div className="mt-12 grid gap-4 md:grid-cols-3">
            {problems.map((item) => (
              <Panel key={item.title} className="reveal p-6">
                <h3 className="font-medium">{item.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{item.body}</p>
              </Panel>
            ))}
          </div>
        </Container>
      </section>

      {/* Lifecycle */}
      <section aria-labelledby="lifecycle" className="border-t border-line py-24">
        <Container>
          <SectionHeading id="lifecycle" eyebrow="How it works" title="One experiment, six explicit phases.">
            Each phase records its evidence before the next begins, so a run can be reviewed step by step and
            resumed after a restart.
          </SectionHeading>
          <ol className="mt-12 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
            {PHASES.map((phase, i) => (
              <li key={phase.id} className="reveal bg-surface p-6">
                <p className="font-mono text-xs text-accent">{String(i + 1).padStart(2, "0")}</p>
                <h3 className="mt-3 font-medium">{phase.name}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{phase.summary}</p>
              </li>
            ))}
          </ol>
          <Link href="/how-it-works" className="mt-8 inline-block text-sm text-accent hover:underline">
            Read the full lifecycle →
          </Link>
        </Container>
      </section>

      {/* Safety */}
      <section aria-labelledby="safety" className="border-t border-line py-24">
        <Container className="grid gap-12 lg:grid-cols-2 lg:items-start">
          <SectionHeading id="safety" eyebrow="Safety model" title="Unsafe experiments never reach the cluster.">
            Policies are defined in code and selected only by target namespace. The server validates every
            experiment statically and against the live workload. AutoResilience writes nothing to the cluster
            except its own ChaosEngines.
          </SectionHeading>
          <Panel className="reveal divide-y divide-line">
            {safety.map((rule) => (
              <div key={rule} className="flex items-center gap-3 px-5 py-3.5 text-sm">
                <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-success" />
                {rule}
              </div>
            ))}
          </Panel>
        </Container>
      </section>

      {/* Evidence and score */}
      <section aria-labelledby="score" className="border-t border-line py-24">
        <Container className="grid gap-12 lg:grid-cols-2 lg:items-start">
          <SectionHeading id="score" eyebrow="Evidence and score" title="A score you can take apart.">
            The Resilience Score is computed only from stored evidence, with no I/O and no model in the loop.
            Each score records its methodology version, and older versions can be recomputed from the same
            evidence.
          </SectionHeading>
          <Panel className="reveal p-6">
            <div className="flex items-baseline justify-between">
              <h3 className="font-medium">Methodology v3 weights</h3>
              <span className="font-mono text-xs text-faint">of 100</span>
            </div>
            <dl className="mt-5 space-y-4">
              {SCORE_V3.map((component) => (
                <div key={component.name}>
                  <div className="flex justify-between text-sm">
                    <dt className="text-muted">{component.name}</dt>
                    <dd className="font-mono tabular-nums">{component.weight}</dd>
                  </div>
                  <div aria-hidden className="mt-1.5 h-1 rounded-full bg-surface-3">
                    <div className="h-1 rounded-full bg-accent" style={{ width: `${component.weight}%` }} />
                  </div>
                </div>
              ))}
            </dl>
            <ul className="mt-6 space-y-2 border-t border-line pt-5 text-sm text-muted">
              <li>A target that did not recover is capped at 40.</li>
              <li>Platform problems are reported as not scored, never blamed on the application.</li>
              <li>Components without data are excluded and the weights re-normalised, visibly.</li>
            </ul>
          </Panel>
        </Container>
      </section>

      {/* Status */}
      <section aria-labelledby="status" className="border-t border-line py-24">
        <Container>
          <SectionHeading id="status" eyebrow="Status" title="Where the project is today.">
            AutoResilience runs end to end on a local kind cluster from source. Packaging and the public
            playground come next.
          </SectionHeading>
          <div className="mt-12 grid gap-4 md:grid-cols-2">
            <Panel className="reveal p-6">
              <StatusBadge status="available" />
              <ul className="mt-4 space-y-2 text-sm text-muted">
                <li>Safety validation, baseline, pod-delete, observation and recovery</li>
                <li>Resilience Score v3 with v1 and v2 recomputation</li>
                <li>Web console: builder, live experiment room, history, services, reports</li>
                <li>Read-only export of completed runs as sanitized recordings</li>
              </ul>
            </Panel>
            <Panel className="reveal p-6">
              <StatusBadge status="planned" />
              <ul className="mt-4 space-y-2 text-sm text-muted">
                <li>Playground replaying real recorded experiments</li>
                <li>Packaged local stack with a guided setup</li>
                <li>Importing your own Kubernetes or Compose application</li>
                <li>Documentation site</li>
              </ul>
            </Panel>
          </div>
        </Container>
      </section>

      {/* CTA */}
      <section aria-labelledby="cta" className="py-12">
        <Container>
          <Panel className="reveal flex flex-col items-start gap-6 p-8 sm:p-10 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 id="cta" className="text-2xl font-semibold tracking-tight">
                See exactly what happens during a run.
              </h2>
              <p className="mt-2 text-muted">Every phase, check and score component, explained.</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <ButtonLink href="/how-it-works" variant="primary">
                How it works
              </ButtonLink>
              <ButtonLink href="/download">Run it from source</ButtonLink>
            </div>
          </Panel>
        </Container>
      </section>
    </>
  );
}
