"use client";

import type { ReactNode } from "react";

import { ChecksTable } from "@/components/experiment/checks-table";
import { ImpactRecovery } from "@/components/experiment/room/impact-recovery";
import { MetricsTable } from "@/components/experiment/room/metrics-table";
import { OutcomeBanner } from "@/components/experiment/room/outcome-banner";
import { ScorePanel } from "@/components/experiment/room/score-panel";
import { ExperimentStateBadge } from "@/components/experiment/state-badge";
import { Badge } from "@/components/ui/badge";
import { Button, ButtonLink } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { ApiError } from "@/lib/api/client";
import { useExperiment } from "@/lib/api/queries";
import { policyName, readImpact, readOrchestration, readRecovery } from "@/lib/evidence";
import { isTerminal, presentState } from "@/lib/experiment-state";
import { formatDateTime, formatSeconds } from "@/lib/format";

function Section({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="grid gap-3">
      <h2 className="flex items-baseline gap-2 border-b border-line pb-1.5 text-sm font-semibold break-after-avoid">
        <span className="font-mono text-xs text-faint">{String(n).padStart(2, "0")}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

const muted = (text: string) => <p className="text-xs text-muted">{text}</p>;

/** A single experiment's report, composed from recorded evidence only. Print-friendly. */
export function ReportView({ id }: { id: string }) {
  const { data: e, isPending, isError, error, refetch } = useExperiment(id);
  if (isPending) return <Card><LoadingState rows={8} label="Loading report" /></Card>;
  if (isError) {
    return (
      <Card>
        {error instanceof ApiError && error.status === 404 ? (
          <EmptyState title="Experiment not found" description={`No experiment with id ${id} exists.`} action={<ButtonLink href="/reports">All reports</ButtonLink>} />
        ) : (
          <ErrorState title="Could not load this report" message={error.message} onRetry={() => refetch()} />
        )}
      </Card>
    );
  }

  const orch = readOrchestration(e);
  const impact = readImpact(e);
  const recovery = readRecovery(e);
  const v = e.validation_result;
  const b = e.baseline;
  const score = e.score?.score;
  return (
    <article className="mx-auto grid max-w-5xl gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-2xs font-medium tracking-wide text-faint uppercase">Resilience experiment report</p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight">{e.name}</h1>
          <p className="mt-1 font-mono text-xs text-muted">
            {e.target.kind} {e.target.namespace}/{e.target.name} · {e.id}
          </p>
          <p className="mt-1 text-xs text-faint">From data recorded up to {formatDateTime(e.updated_at)}</p>
        </div>
        <div className="flex gap-2 print:hidden">
          <ButtonLink href={`/experiments/${e.id}`}>Experiment room</ButtonLink>
          <Button variant="primary" onClick={() => window.print()}>
            Print / save as PDF
          </Button>
        </div>
      </header>

      {!isTerminal(e.state) ? (
        <Callout tone="info" title="Provisional report">
          This experiment is still {presentState(e).label.toLowerCase()}; sections fill in as evidence is recorded.
        </Callout>
      ) : null}

      <Section n={1} title="Summary">
        <Card>
          <CardBody>
            <DescriptionList
              items={[
                { label: "Outcome", value: <ExperimentStateBadge experiment={e} /> },
                {
                  label: "Resilience score",
                  value:
                    score !== null && score !== undefined ? (
                      <span className="font-mono">
                        {score.toFixed(1)} / 100 {e.score?.rating ? <Badge>{e.score.rating}</Badge> : null}
                      </span>
                    ) : e.score ? (
                      "Not scored"
                    ) : (
                      "—"
                    ),
                },
                { label: "Time to recovery", value: formatSeconds(recovery?.timeToRecoverySeconds) },
                {
                  label: "Client outage",
                  value:
                    impact?.client?.outage?.status === "OK"
                      ? `${formatSeconds(impact.client.outage.seconds)} (${impact.client.outage.pattern?.toLowerCase()})`
                      : "—",
                },
                {
                  label: "Client failures",
                  value:
                    impact?.client?.requests !== null && impact?.client?.requests !== undefined
                      ? `${impact.client.failed ?? 0} of ${impact.client.requests}`
                      : "—",
                },
                { label: "Litmus verdict", value: String((e.observation?.litmus as { verdict?: string } | undefined)?.verdict ?? "—") },
              ]}
            />
          </CardBody>
        </Card>
        <OutcomeBanner experiment={e} orch={orch} />
      </Section>

      <Section n={2} title="Configuration">
        <Card>
          <CardBody>
            <DescriptionList
              items={[
                { label: "Target", value: <span className="font-mono text-xs">{e.target.kind} {e.target.namespace}/{e.target.name}</span> },
                { label: "Fault", value: `${e.fault_type} · ${e.pod_delete_mode}` },
                { label: "Blast radius", value: `${e.affected_replicas} replica(s) for ${e.duration_seconds}s` },
                { label: "Safety policy", value: policyName(e) ?? "—" },
                { label: "Orchestration", value: orch.mode === "auto" ? `Automatic (started ${formatDateTime(orch.requestedAt)})` : "Manual" },
                { label: "Created", value: formatDateTime(e.created_at) },
                { label: "Description", value: e.description || "—" },
              ]}
            />
          </CardBody>
        </Card>
      </Section>

      <Section n={3} title="Safety validation">
        {v ? (
          <>
            <p className="text-xs text-muted">
              <Badge tone={v.passed ? "success" : "danger"} dot>{v.passed ? "Passed" : "Blocked"}</Badge>{" "}
              Policy “{policyName(e) ?? "—"}”: {v.policy_selection?.rule ?? "—"}.
            </p>
            <ChecksTable title="Static checks" description="Configuration against the policy" checks={v.static_checks} />
            <ChecksTable title="Cluster checks" description="Live Kubernetes state at validation time" checks={v.cluster_checks} />
          </>
        ) : (
          muted("Not validated.")
        )}
      </Section>

      <Section n={4} title="Baseline and measurements">
        {b ? (
          <>
            {muted(`Baseline ${b.status.toLowerCase()} at ${formatDateTime(b.captured_at)} over ${b.window_seconds}s.${b.failure_reasons.length ? ` ${b.failure_reasons.join("; ")}` : ""}`)}
            <MetricsTable experiment={e} />
          </>
        ) : (
          muted("No baseline was captured: the experiment ended before the baseline stage.")
        )}
      </Section>

      <Section n={5} title="Fault, impact and recovery">
        <ImpactRecovery experiment={e} />
        {e.observation ? muted(`Recovery rule: ${e.observation.rule}`) : null}
      </Section>

      <Section n={6} title="Resilience Score">
        <ScorePanel experiment={e} />
      </Section>
    </article>
  );
}
