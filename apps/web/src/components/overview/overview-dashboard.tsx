"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { ScoreCell } from "@/components/experiment/score-cell";
import { ExperimentStateBadge } from "@/components/experiment/state-badge";
import { Badge, type Tone } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useDashboardSummary } from "@/lib/api/queries";
import type { DashboardSummary } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatRelative, formatSeconds } from "@/lib/format";

import { ScoreTrend } from "./score-trend";

const RATING_TONE: Record<string, Tone> = { Excellent: "success", Good: "success", Fair: "warning", Poor: "danger" };

function Stat({ label, value, href, tone }: { label: string; value: number; href: string; tone?: string }) {
  return (
    <Link href={href} className="group min-w-0 px-4 py-3 hover:bg-surface-2/60">
      <p className="text-2xs font-medium tracking-wide text-faint uppercase">{label}</p>
      <p className={cn("mt-1 font-mono text-2xl font-semibold tabular-nums", value ? tone : "text-faint")}>{value}</p>
    </Link>
  );
}

function OutcomeStrip({ s }: { s: DashboardSummary }) {
  const o = s.outcomes;
  return (
    <section
      aria-label="Experiment outcomes"
      className="grid grid-cols-2 divide-line rounded-lg border border-line bg-surface sm:grid-cols-3 sm:divide-x lg:grid-cols-6"
    >
      <Stat label="Experiments" value={s.total} href="/experiments" tone="text-fg" />
      <Stat label="Not finished" value={o.active} href="/experiments?state=active" tone="text-info" />
      <Stat label="Completed" value={o.completed} href="/experiments?state=completed" tone="text-success" />
      <Stat label="Failed" value={o.failed} href="/experiments?state=failed" tone="text-danger" />
      <Stat label="Aborted" value={o.aborted} href="/experiments?state=aborted" tone="text-fg" />
      <Stat label="Undetermined" value={o.undetermined} href="/experiments?state=undetermined" tone="text-warning" />
    </section>
  );
}

function Figure({ value, unit, caption }: { value: string; unit?: string; caption: ReactNode }) {
  return (
    <div>
      <p className="font-mono text-3xl font-semibold tabular-nums">
        {value}
        {unit ? <span className="ml-1 text-sm font-normal text-faint">{unit}</span> : null}
      </p>
      <p className="mt-1 text-xs text-muted">{caption}</p>
    </div>
  );
}

function ScoreSummary({ s }: { s: DashboardSummary }) {
  const sc = s.scores;
  const notes = [
    sc.not_recovered ? `${sc.not_recovered} did not recover (capped)` : null,
    sc.not_scored ? `${sc.not_scored} not scored (undetermined)` : null,
    sc.other_versions ? `${sc.other_versions} scored with an older methodology, excluded` : null,
  ].filter(Boolean);
  return (
    <Card>
      <CardHeader title="Resilience Score" description={`Methodology ${sc.version}`} />
      <CardBody className="grid gap-3">
        {sc.count ? (
          <>
            <Figure
              value={sc.average!.toFixed(1)}
              unit="avg"
              caption={`${sc.count} scored run${sc.count === 1 ? "" : "s"} · range ${sc.minimum!.toFixed(1)}–${sc.maximum!.toFixed(1)}`}
            />
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(sc.by_rating).map(([rating, n]) => (
                <Badge key={rating} tone={RATING_TONE[rating] ?? "neutral"}>
                  {rating} · {n}
                </Badge>
              ))}
            </div>
          </>
        ) : (
          <p className="text-xs text-muted">No scored runs yet. A score is recorded when an experiment completes.</p>
        )}
        {notes.length ? <p className="text-2xs text-faint">{notes.join(" · ")}</p> : null}
      </CardBody>
    </Card>
  );
}

function DistributionCard({
  title,
  description,
  d,
  empty,
}: {
  title: string;
  description: string;
  d: DashboardSummary["recovery_time_seconds"];
  empty: string;
}) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <CardBody>
        {d.count ? (
          <Figure
            value={formatSeconds(d.median).replace(/ s$/, "")}
            unit={/ s$/.test(formatSeconds(d.median)) ? "s median" : "median"}
            caption={`${d.count} run${d.count === 1 ? "" : "s"} · min ${formatSeconds(d.minimum)} · max ${formatSeconds(d.maximum)}`}
          />
        ) : (
          <p className="text-xs text-muted">{empty}</p>
        )}
      </CardBody>
    </Card>
  );
}

function Recent({ s }: { s: DashboardSummary }) {
  return (
    <Card>
      <CardHeader title="Recent experiments" actions={<ButtonLink href="/experiments" size="sm" variant="ghost">All experiments</ButtonLink>} />
      <Table>
        <THead>
          <tr>
            <TH>Experiment</TH>
            <TH>State</TH>
            <TH className="text-right">Score</TH>
            <TH>Outcome</TH>
            <TH>Created</TH>
          </tr>
        </THead>
        <TBody>
          {s.recent.map((e) => (
            <TR key={e.id}>
              <TD>
                <Link href={`/experiments/${e.id}`} className="text-xs font-medium hover:text-accent">{e.name}</Link>
                <div className="font-mono text-2xs text-faint">{e.target.namespace}/{e.target.name} · {e.pod_delete_mode}</div>
              </TD>
              <TD><ExperimentStateBadge experiment={e} /></TD>
              <TD className="text-right"><ScoreCell score={e.score} /></TD>
              <TD className="max-w-80 truncate text-xs text-muted" title={e.outcome_reason ?? undefined}>{e.outcome_reason ?? "—"}</TD>
              <TD className="text-xs text-muted">{formatRelative(e.created_at)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}

function Namespaces({ s }: { s: DashboardSummary }) {
  return (
    <Card>
      <CardHeader title="Namespaces tested" description="From experiment targets" />
      <Table>
        <THead>
          <tr>
            <TH>Namespace</TH>
            <TH className="text-right">Runs</TH>
            <TH className="text-right">Completed</TH>
            <TH>Last activity</TH>
          </tr>
        </THead>
        <TBody>
          {s.namespaces.map((n) => (
            <TR key={n.namespace}>
              <TD className="font-mono text-xs">
                <Link href={`/experiments?ns=${encodeURIComponent(n.namespace)}`} className="hover:text-accent">{n.namespace}</Link>
              </TD>
              <TD className="text-right font-mono text-xs tabular-nums">{n.total}</TD>
              <TD className="text-right font-mono text-xs tabular-nums">{n.completed}</TD>
              <TD className="text-xs text-muted">{formatRelative(n.last_activity)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}

/** Overview built from GET /dashboard/summary; every number is a backend aggregate. */
export function OverviewDashboard() {
  const { data: s, isPending, isError, error, refetch } = useDashboardSummary();
  if (isPending) return <Card><LoadingState rows={6} label="Loading overview" /></Card>;
  if (isError) return <Card><ErrorState message={error.message} onRetry={() => refetch()} /></Card>;
  if (s.total === 0) {
    return (
      <Card>
        <EmptyState
          title="No experiments yet"
          description="After the first runs this page shows outcome counts, the Resilience Score summary, recovery and client-outage times, the score of each run and the namespaces you have tested."
          action={<ButtonLink href="/experiments/new" variant="primary" size="sm">Run your first experiment</ButtonLink>}
        />
      </Card>
    );
  }
  return (
    <div className="grid gap-4">
      <OutcomeStrip s={s} />
      <div className="grid gap-4 lg:grid-cols-3">
        <ScoreSummary s={s} />
        <DistributionCard
          title="Time to recovery"
          description="Completed runs · replacement created → Ready"
          d={s.recovery_time_seconds}
          empty="No completed run with a measured recovery yet."
        />
        <DistributionCard
          title="Client-observed outage"
          description="Runs with load-generator outage evidence"
          d={s.client_outage_seconds}
          empty="No run with client outage evidence yet."
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ScoreTrend points={s.score_history} version={s.scores.version} />
        </div>
        <Namespaces s={s} />
      </div>
      <Recent s={s} />
    </div>
  );
}
