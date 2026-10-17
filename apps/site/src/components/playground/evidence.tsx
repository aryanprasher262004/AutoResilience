import { Badge, type Tone } from "@autoresilience/ui/badge";
import { cn } from "@autoresilience/ui/cn";
import type { ReactNode } from "react";

import { ExternalLink } from "@/components/primitives";
import { utc } from "@/lib/recordings/replay";
import type { RecordedExperiment, RecordedValidation, ScoreComponent } from "@/lib/recordings/types";
import { commitUrl, repoFile } from "@/lib/site";

type AnyRecorded = RecordedExperiment | RecordedValidation;

const CATEGORY: Record<AnyRecorded["provenance"]["evidence_category"], string> = {
  development_run: "Development run",
  controlled_research: "Controlled research run",
};

/** Shown on every playground page that renders evidence. */
export function RecordingBanner({ recording }: { recording: AnyRecorded }) {
  const p = recording.provenance;
  return (
    <div role="note" className="rounded-xl border border-accent/30 bg-accent/5 px-4 py-3 text-sm">
      <p className="flex flex-wrap items-center gap-2">
        <Badge tone="info" dot>
          Recorded experiment
        </Badge>
        <Badge tone="warning">{CATEGORY[p.evidence_category]}</Badge>
        {p.evidence_level === "A" ? <Badge tone="success">Level A</Badge> : <Badge>Unclassified evidence</Badge>}
      </p>
      <p className="mt-2 leading-relaxed text-muted">
        {recording.schema === "autoresilience-validation/1"
          ? `A real safety validation recorded ${utc(p.captured_at)} on ${p.environment}.`
          : `A real run captured ${utc(p.captured_at)} on ${p.environment}.`}{" "}
        Nothing is executed: this page replays exported evidence and connects to nothing.
        {p.evidence_category === "development_run"
          ? " It is a development run, not controlled research evidence."
          : null}
      </p>
    </div>
  );
}

export function Section({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-xl border border-line bg-surface", className)}>
      <h2 className="border-b border-line px-4 py-3 text-sm font-medium sm:px-5">{title}</h2>
      <div className="px-4 py-4 sm:px-5">{children}</div>
    </section>
  );
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="divide-y divide-line text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-4 py-2">
          <dt className="text-muted">{label}</dt>
          <dd className="min-w-0 break-words">{value ?? <span className="text-faint">Not recorded</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

const mono = (value: ReactNode) => <span className="font-mono tabular-nums">{value}</span>;

export function ClientImpactPanel({ recording }: { recording: RecordedExperiment }) {
  const client = recording.experiment.impact.client;
  if (!client || client.status !== "OK") {
    return (
      <Section title="Client impact">
        <p className="text-sm text-muted">No client-side load generator measured this workload.</p>
      </Section>
    );
  }
  const outage = client.outage;
  return (
    <Section title="Client impact">
      <Rows
        rows={[
          ["Requests in window", mono(client.requests)],
          [
            "Failed requests",
            <>
              {mono(client.failed)}
              {client.failure_ratio !== null ? <span className="text-faint"> (ratio {client.failure_ratio})</span> : null}
            </>,
          ],
          [
            "By outcome",
            <span key="o" className="font-mono text-xs">
              {client.http_error ?? 0} HTTP error · {client.connection_error ?? 0} connection error · {client.timeout ?? 0} timeout
            </span>,
          ],
          ["Outage pattern", outage ? <Badge tone={outage.pattern === "NONE" ? "success" : "warning"}>{outage.pattern}</Badge> : null],
          ["Outage duration", outage?.outage_seconds !== null && outage ? mono(`${outage.outage_seconds} s`) : null],
          ["Counted", client.counted_from && client.counted_to ? `${utc(client.counted_from)} → ${utc(client.counted_to).slice(11)}` : null],
        ]}
      />
      <p className="mt-3 text-xs leading-relaxed text-faint">
        Measured by the built-in load generator from the client’s side; counts are exact counter
        differences, intervals have scrape (15 s) resolution.
      </p>
    </Section>
  );
}

export function RecoveryPanel({ recording }: { recording: RecordedExperiment }) {
  const run = recording.experiment;
  const r = run.recovery;
  return (
    <Section title="Recovery evidence">
      <Rows
        rows={[
          ["Decision", <Badge key="d" tone="success" dot>{run.outcome.status} · {run.outcome.reason_code}</Badge>],
          ["Time to recovery", mono(`${r.time_to_recovery_seconds} s`)],
          ["Replacement created", mono(utc(r.fault_observed_at))],
          ["Replacements Ready", mono(utc(r.recovered_at))],
          ["Confirmed stable", mono(utc(r.confirmed_at))],
          ["Stable samples", mono(r.stable_streak.length)],
          ["Lowest availability", mono(`${run.impact.min_available_replicas ?? "?"} replica(s)`)],
          ["Container restarts", mono(run.impact.restarts_in_window ?? "not recorded")],
          ["Litmus verdict", <Badge key="l" tone={run.litmus.verdict === "Pass" ? "success" : "danger"}>{run.litmus.verdict}</Badge>],
        ]}
      />
      <p className="mt-3 text-xs leading-relaxed text-faint">Rule: {r.rule}.</p>
    </Section>
  );
}

const COMPONENT_NAMES: Record<string, string> = {
  recovery_time: "Recovery time",
  client_outage: "Client outage",
  request_failures: "Request failures",
  restarts: "Restarts",
  litmus_verdict: "Litmus verdict",
  availability: "Availability",
  error_ratio: "Error ratio",
};

export function ScorePanel({ recording }: { recording: RecordedExperiment }) {
  const score = recording.experiment.score;
  const tone: Tone = score.score >= 90 ? "success" : score.score >= 75 ? "info" : score.score >= 50 ? "warning" : "danger";
  return (
    <section aria-labelledby="score-title" className="rounded-xl border border-line bg-surface">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line px-4 py-4 sm:px-5">
        <div>
          <h2 id="score-title" className="text-sm font-medium">
            Resilience Score
          </h2>
          <p className="mt-1 text-xs text-faint">
            Methodology {score.version} ·{" "}
            <ExternalLink href={repoFile(`docs/scoring/resilience-score-${score.version}.md`)} className="text-accent hover:underline">
              how it is computed
            </ExternalLink>
          </p>
        </div>
        <p className="flex items-baseline gap-2">
          <span className="font-mono text-4xl font-semibold tabular-nums">{score.score}</span>
          <span className="text-faint">/ 100</span>
          <Badge tone={tone}>{score.rating}</Badge>
        </p>
      </div>
      <div className="px-4 py-4 sm:px-5">
        <p className="text-sm leading-relaxed text-muted">{score.explanation}</p>
        <ul className="mt-5 space-y-4">
          {score.components.map((c) => (
            <ComponentRow key={c.name} component={c} />
          ))}
        </ul>
      </div>
    </section>
  );
}

function ComponentRow({ component: c }: { component: ScoreComponent }) {
  const applicable = c.status === "SCORED";
  const lost = applicable ? c.effective_weight - c.contribution : 0;
  return (
    <li>
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
        <span>{COMPONENT_NAMES[c.name] ?? c.name}</span>
        <span className="font-mono text-xs tabular-nums text-muted">
          {applicable ? (
            <>
              {c.contribution.toFixed(1)} / {c.effective_weight.toFixed(1)}
              {lost > 0.05 ? <span className="text-warning"> (−{lost.toFixed(1)})</span> : null}
            </>
          ) : (
            "not applicable"
          )}
        </span>
      </div>
      <div
        className="mt-1.5 flex h-1.5 overflow-hidden rounded-full bg-surface-3"
        role="img"
        aria-label={applicable ? `${c.contribution.toFixed(1)} of ${c.effective_weight.toFixed(1)} points` : "Not applicable"}
      >
        <div className="bg-accent" style={{ width: `${c.contribution}%` }} />
        <div className="bg-warning/50" style={{ width: `${lost}%` }} />
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-faint">{c.reason}</p>
    </li>
  );
}

export function ValidationChecks({ recording }: { recording: AnyRecorded }) {
  const v = recording.experiment.validation;
  const checks = v.checks as { phase: string; name: string; status: string; message?: string | null }[];
  const tone: Record<string, Tone> = { PASSED: "success", FAILED: "danger", ERROR: "warning", SKIPPED: "neutral" };
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <caption className="sr-only">Safety checks</caption>
        <thead className="text-2xs text-faint">
          <tr>
            <th scope="col" className="py-2 pr-3 font-normal">Check</th>
            <th scope="col" className="py-2 pr-3 font-normal">Phase</th>
            <th scope="col" className="py-2 font-normal">Result</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {checks.map((c) => (
            <tr key={`${c.phase}-${c.name}`}>
              <td className="py-2 pr-3 align-top">
                <span className="font-mono text-xs">{c.name}</span>
                {c.message ? <span className="mt-0.5 block text-xs text-faint">{c.message}</span> : null}
              </td>
              <td className="py-2 pr-3 align-top text-muted">{c.phase}</td>
              <td className="py-2 align-top">
                <Badge tone={tone[c.status] ?? "neutral"} dot>
                  {c.status}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PolicyRows({ recording }: { recording: AnyRecorded }) {
  const p = recording.experiment.validation.policy;
  return (
    <Rows
      rows={[
        ["Policy", mono(p.name)],
        ["Max duration", mono(`${p.max_duration_seconds} s`)],
        ["Max affected replicas", mono(p.max_affected_replicas)],
        ["Min healthy replicas", mono(p.min_healthy_replicas)],
        ["Allowed namespaces", p.allowed_namespaces ? mono(p.allowed_namespaces.join(", ")) : "Any not forbidden"],
        ["Forbidden namespaces", <span key="f" className="font-mono text-xs">{p.forbidden_namespaces.join(", ")}</span>],
      ]}
    />
  );
}

export function ProvenanceRows({ recording }: { recording: AnyRecorded }) {
  const p = recording.provenance;
  return (
    <Rows
      rows={[
        ["Recording", mono(recording.recording_id)],
        ["Schema", mono(recording.schema)],
        ["Evidence category", CATEGORY[p.evidence_category]],
        ["Evidence level", p.evidence_level === "A" ? "Level A (reviewed)" : "Unclassified"],
        ["Synthetic", p.synthetic ? "Yes" : "No, a real run"],
        ["Captured", mono(utc(p.captured_at))],
        ["Exported", mono(utc(p.exported_at))],
        ["Environment", p.environment],
        [
          "Engine commit",
          <ExternalLink key="c" href={commitUrl(p.engine_commit)} className="font-mono text-xs text-accent hover:underline">
            {p.engine_commit.slice(0, 12)}
          </ExternalLink>,
        ],
        ["Exporter", mono(p.exporter_version)],
        ...("score_version" in p ? [["Score version", mono(p.score_version)] as [string, ReactNode]] : []),
        [
          "Integrity (sha256)",
          <span key="h" className="font-mono text-xs break-all">
            {recording.integrity.content_sha256}
          </span>,
        ],
      ]}
    />
  );
}

/** Collapsible technical evidence; closed by default. */
export function Details({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="group rounded-xl border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium sm:px-5 [&::-webkit-details-marker]:hidden">
        {title}
        <span aria-hidden className="text-faint group-open:rotate-90 motion-safe:transition-transform">
          ›
        </span>
      </summary>
      <div className="border-t border-line px-4 py-4 sm:px-5">{children}</div>
    </details>
  );
}

export function RawJson({ value }: { value: unknown }) {
  return (
    <pre tabIndex={0} className="max-h-[32rem] overflow-auto rounded-lg bg-canvas p-4 font-mono text-xs leading-relaxed text-muted">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function BaselineRows({ recording }: { recording: RecordedExperiment }) {
  const b = recording.experiment.baseline;
  const groups = { availability: b.availability, restarts: b.restarts, requests: b.requests, client: b.client };
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        {b.status} at {utc(b.captured_at)} over a {b.window_seconds} s window.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {Object.entries(groups).map(([name, group]) => (
          <div key={name} className="rounded-lg border border-line p-3">
            <p className="flex items-center justify-between text-sm">
              <span className="capitalize">{name}</span>
              <Badge tone={group?.status === "OK" ? "success" : "neutral"}>{group?.status ?? "NOT RECORDED"}</Badge>
            </p>
            {group ? (
              <dl className="mt-2 space-y-1 text-xs">
                {Object.entries(group.values).map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-3">
                    <dt className="text-faint">{key}</dt>
                    <dd className="font-mono tabular-nums">{value ?? "—"}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
