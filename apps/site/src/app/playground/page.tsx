import { Badge } from "@autoresilience/ui/badge";
import type { Metadata } from "next";
import Link from "next/link";

import { ButtonLink, Container, ExternalLink, PageHeader, Panel, StatusBadge } from "@/components/primitives";
import { describeWorkload, sortRecordings } from "@/lib/recordings/catalog";
import { loadRecordings } from "@/lib/recordings/load";
import { utc } from "@/lib/recordings/replay";
import type { RecordedExperiment, RecordedValidation, Recording, RejectedFile } from "@/lib/recordings/types";
import { repoFile } from "@/lib/site";

export const metadata: Metadata = { title: "Playground" };

export default function PlaygroundPage() {
  const { recordings, rejected } = loadRecordings();
  const sorted = sortRecordings(recordings);
  const experiments = sorted.filter((r): r is Recording & { kind: "experiment" } => r.kind === "experiment");
  const validations = sorted.filter((r): r is Recording & { kind: "validation" } => r.kind === "validation");

  return (
    <>
      <PageHeader
        eyebrow="Playground"
        title="Replay real experiments, step by step."
        status={recordings.length ? <Badge tone="info" dot>Recorded evidence</Badge> : <StatusBadge status="planned">Coming soon</StatusBadge>}
      >
        <p>
          Each replay is a sanitized, hash-verified recording of a real run on a local kind cluster: the
          lifecycle, the deleted pod and its replacement, what clients saw, and how the score was computed.
          Nothing is executed and nothing connects to a cluster.
        </p>
      </PageHeader>
      <Container className="space-y-12 py-16">
        {rejected.length ? <RejectedNotice rejected={rejected} /> : null}
        {recordings.length === 0 ? <EmptyState /> : null}

        {experiments.length ? (
          <section aria-labelledby="choose">
            <h2 id="choose" className="text-2xl font-semibold tracking-tight">
              Choose a workload
            </h2>
            <p className="mt-2 max-w-2xl text-muted">
              The same pod-delete against a redundant service and a deliberately fragile single-replica one.
            </p>
            <ul className="mt-8 grid gap-4 md:grid-cols-2">
              {experiments.map((r) => (
                <li key={r.id}>
                  <ExperimentCard id={r.id} data={r.data} />
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {validations.length ? (
          <section aria-labelledby="safety-evidence">
            <h2 id="safety-evidence" className="text-2xl font-semibold tracking-tight">
              Safety evidence
            </h2>
            <p className="mt-2 max-w-2xl text-muted">Experiments the safety model refused before anything was injected.</p>
            <ul className="mt-8 grid gap-4 md:grid-cols-2">
              {validations.map((r) => (
                <li key={r.id}>
                  <ValidationCard id={r.id} data={r.data} />
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {recordings.length ? (
          <p className="max-w-3xl text-sm leading-relaxed text-faint">
            These are development runs exported with the read-only recorder, not controlled research
            evidence, and their evidence level is unclassified. Pod names are aliases. Format and checks:{" "}
            <ExternalLink href={repoFile("docs/recordings.md")} className="text-accent hover:underline">
              recording contract
            </ExternalLink>
            .
          </p>
        ) : null}
      </Container>
    </>
  );
}

function ExperimentCard({ id, data }: { id: string; data: RecordedExperiment }) {
  const w = describeWorkload(data);
  const run = data.experiment;
  const client = run.impact.client;
  const outage = client?.outage;
  return (
    <Link href={`/playground/${id}`} className="group block h-full rounded-xl focus-visible:outline-offset-4">
      <Panel className="h-full p-6 transition-colors group-hover:border-line-strong">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={w.replicas !== null && w.replicas > 1 ? "success" : "warning"}>{w.profile}</Badge>
          <Badge>{w.replicas ?? "?"} replica{w.replicas === 1 ? "" : "s"}</Badge>
        </div>
        <h3 className="mt-4 font-mono text-lg group-hover:text-accent">{w.title}</h3>
        <p className="mt-1 text-sm text-muted">{w.fault}, {run.fault.duration_seconds} s</p>
        <dl className="mt-6 grid grid-cols-3 gap-3 text-sm">
          <div>
            <dt className="text-2xs text-faint">Score ({run.score.version})</dt>
            <dd className="mt-1 font-mono text-xl tabular-nums">{run.score.score}</dd>
          </div>
          <div>
            <dt className="text-2xs text-faint">Time to recovery</dt>
            <dd className="mt-1 font-mono text-xl tabular-nums">{run.recovery.time_to_recovery_seconds} s</dd>
          </div>
          <div>
            <dt className="text-2xs text-faint">Client outage</dt>
            <dd className="mt-1 font-mono text-xl tabular-nums">
              {outage && outage.outage_seconds !== null ? `${outage.outage_seconds} s` : "—"}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-faint">
          {client?.status === "OK" ? `${client.failed} of ${client.requests} client requests failed · ` : ""}
          captured {utc(data.provenance.captured_at)}
        </p>
        <p className="mt-5 text-sm text-accent">Replay this run →</p>
      </Panel>
    </Link>
  );
}

function ValidationCard({ id, data }: { id: string; data: RecordedValidation }) {
  const run = data.experiment;
  const failed = run.validation.checks.filter((c) => c.status !== "PASSED");
  return (
    <Link href={`/playground/${id}`} className="group block h-full rounded-xl focus-visible:outline-offset-4">
      <Panel className="h-full p-6 transition-colors group-hover:border-line-strong">
        <Badge tone="danger" dot>
          Rejected before injection
        </Badge>
        <h3 className="mt-4 font-mono text-lg group-hover:text-accent">
          {run.target.namespace}/{run.target.name}
        </h3>
        <p className="mt-1 text-sm text-muted">
          {run.target.kind} · {run.fault.type} of {run.fault.affected_replicas} replica · policy “{run.validation.policy.name}”
        </p>
        <ul className="mt-4 space-y-1 text-sm">
          {failed.map((c) => (
            <li key={c.name} className="font-mono text-xs text-danger">
              {c.status} {c.name}
            </li>
          ))}
        </ul>
        <p className="mt-5 text-sm text-accent">See the checks →</p>
      </Panel>
    </Link>
  );
}

function RejectedNotice({ rejected }: { rejected: RejectedFile[] }) {
  return (
    <div role="alert" className="rounded-xl border border-danger/40 bg-danger/5 p-5">
      <p className="font-medium text-danger">
        {rejected.length} recording file{rejected.length === 1 ? "" : "s"} failed verification and {rejected.length === 1 ? "is" : "are"} not shown
      </p>
      <ul className="mt-2 space-y-1 text-sm text-muted">
        {rejected.map((r) => (
          <li key={r.file}>
            <span className="font-mono text-xs">{r.file}</span>: {r.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyState() {
  return (
    <Panel className="flex flex-col items-center px-6 py-16 text-center">
      <h2 className="text-xl font-medium">No recordings yet</h2>
      <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted">
        Recordings are exported only from real, completed experiments, then sanitized and
        hash-verified. There is no sample or simulated data.
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <ButtonLink href="/how-it-works" variant="primary">
          How a run works
        </ButtonLink>
      </div>
    </Panel>
  );
}
