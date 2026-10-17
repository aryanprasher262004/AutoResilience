import { Badge } from "@autoresilience/ui/badge";
import { cn } from "@autoresilience/ui/cn";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  BaselineRows,
  ClientImpactPanel,
  Details,
  PolicyRows,
  ProvenanceRows,
  RawJson,
  RecordingBanner,
  RecoveryPanel,
  ScorePanel,
  Section,
  ValidationChecks,
} from "@/components/playground/evidence";
import { Replay } from "@/components/playground/replay";
import { Container } from "@/components/primitives";
import { describeWorkload, sortRecordings } from "@/lib/recordings/catalog";
import { loadRecordings } from "@/lib/recordings/load";
import type { RecordedExperiment, RecordedValidation, Recording } from "@/lib/recordings/types";

export const dynamicParams = false;

export function generateStaticParams() {
  return loadRecordings().recordings.map((r) => ({ recordingId: r.id }));
}

function find(id: string): { recording: Recording; all: Recording[] } {
  const all = sortRecordings(loadRecordings().recordings);
  const recording = all.find((r) => r.id === id);
  if (!recording) notFound();
  return { recording, all };
}

export async function generateMetadata({ params }: PageProps<"/playground/[recordingId]">): Promise<Metadata> {
  const { recording } = find((await params).recordingId);
  const run = recording.data.experiment;
  return { title: `${run.target.namespace}/${run.target.name} · Recorded experiment` };
}

export default async function RecordingPage({ params }: PageProps<"/playground/[recordingId]">) {
  const { recording, all } = find((await params).recordingId);
  return (
    <Container className="space-y-6 pt-28 pb-8 sm:pt-32">
      <nav aria-label="Breadcrumb" className="text-sm text-muted">
        <Link href="/playground" className="hover:text-fg">
          Playground
        </Link>{" "}
        <span aria-hidden>/</span> <span className="font-mono text-xs">{recording.id}</span>
      </nav>
      {recording.kind === "experiment" ? (
        <ExperimentView data={recording.data} id={recording.id} all={all} />
      ) : (
        <ValidationView data={recording.data} />
      )}
    </Container>
  );
}

function ExperimentView({ data, id, all }: { data: RecordedExperiment; id: string; all: Recording[] }) {
  const run = data.experiment;
  const workload = describeWorkload(data);
  const others = all.filter((r): r is Recording & { kind: "experiment" } => r.kind === "experiment");
  return (
    <>
      <header className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="success" dot>
              {run.state}
            </Badge>
            <Badge>{workload.profile}</Badge>
            <Badge>{workload.replicas ?? "?"} desired replica{workload.replicas === 1 ? "" : "s"}</Badge>
          </div>
          <h1 className="mt-3 font-mono text-2xl font-semibold tracking-tight sm:text-3xl">{workload.title}</h1>
          <p className="mt-2 text-muted">
            {run.target.kind} · {run.fault.type} ({run.fault.pod_delete_mode}) of {run.fault.affected_replicas} replica for{" "}
            {run.fault.duration_seconds} s
          </p>
        </div>
        {others.length > 1 ? (
          <nav aria-label="Recorded workloads">
            <ul className="flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1">
              {others.map((r) => {
                const w = describeWorkload(r.data);
                const active = r.id === id;
                return (
                  <li key={r.id}>
                    <Link
                      href={`/playground/${r.id}`}
                      aria-current={active ? "page" : undefined}
                      className={cn("block rounded-lg px-3 py-2 text-sm", active ? "bg-surface-3 text-fg" : "text-muted hover:text-fg")}
                    >
                      <span className="font-mono text-xs">{w.title}</span>
                      <span className="ml-2 text-2xs text-faint">{w.replicas}×</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        ) : null}
      </header>

      <RecordingBanner recording={data} />
      <Replay recording={data} />

      <div className="grid gap-4 lg:grid-cols-2">
        <ClientImpactPanel recording={data} />
        <RecoveryPanel recording={data} />
      </div>
      <ScorePanel recording={data} />

      <div className="space-y-3">
        <h2 className="pt-4 text-sm font-medium text-muted">Technical evidence</h2>
        <Details title="Provenance and integrity">
          <ProvenanceRows recording={data} />
        </Details>
        <Details title={`Safety validation (${run.validation.checks.length} checks passed)`}>
          <ValidationChecks recording={data} />
          <div className="mt-4">
            <PolicyRows recording={data} />
          </div>
        </Details>
        <Details title="Baseline (before the fault)">
          <BaselineRows recording={data} />
        </Details>
        <Details title="Recorded JSON">
          <RawJson value={data} />
        </Details>
      </div>
    </>
  );
}

function ValidationView({ data }: { data: RecordedValidation }) {
  const run = data.experiment;
  const failed = run.validation.checks.filter((c) => c.status !== "PASSED");
  return (
    <>
      <header>
        <Badge tone="danger" dot>
          {run.state}
        </Badge>
        <h1 className="mt-3 font-mono text-2xl font-semibold tracking-tight sm:text-3xl">
          {run.target.namespace}/{run.target.name}
        </h1>
        <p className="mt-2 text-muted">
          {run.target.kind} · requested {run.fault.type} ({run.fault.pod_delete_mode}) of {run.fault.affected_replicas} replica for{" "}
          {run.fault.duration_seconds} s
        </p>
      </header>
      <RecordingBanner recording={data} />
      <Section title="Why it was refused">
        <p className="text-sm leading-relaxed text-muted">
          The safety model refused this experiment: {failed.length} check{failed.length === 1 ? "" : "s"} did not pass.
          No ChaosEngine was created, no baseline was taken and no pod was touched.
        </p>
        <ul className="mt-3 space-y-2">
          {failed.map((c) => (
            <li key={c.name} className="rounded-lg border border-danger/40 bg-danger/5 p-3 text-sm">
              <span className="font-mono text-xs text-danger">
                {c.status} · {c.name}
              </span>
              {c.message ? <span className="mt-1 block text-muted">{c.message}</span> : null}
            </li>
          ))}
        </ul>
      </Section>
      <Section title="All checks">
        <ValidationChecks recording={data} />
      </Section>
      <Section title="Policy applied">
        <PolicyRows recording={data} />
      </Section>
      <Details title="Provenance and integrity">
        <ProvenanceRows recording={data} />
      </Details>
      <Details title="Recorded JSON">
        <RawJson value={data} />
      </Details>
    </>
  );
}
