"use client";

import Link from "next/link";

import { ScoreTrend } from "@/components/overview/score-trend";
import { ScoreCell } from "@/components/experiment/score-cell";
import { ExperimentStateBadge } from "@/components/experiment/state-badge";
import { Badge } from "@/components/ui/badge";
import { ButtonLink } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import { useService } from "@/lib/api/queries";
import type { ServiceDetail as Detail, WorkloadKind } from "@/lib/api/types";
import { WORKLOAD_KINDS } from "@/lib/experiment-options";
import { formatDateTime, formatRelative, formatSeconds, shortId } from "@/lib/format";

import { HealthBadge, Replicas, newExperimentHref } from "./health-badge";

function KubernetesHealth({ s }: { s: Detail }) {
  return (
    <Card>
      <CardHeader title="Kubernetes health" description="Live pod status, read the way safety validation reads it" />
      <CardBody className="grid gap-3">
        {s.cluster_error ? (
          <Callout tone="warning" title="The cluster could not be queried">
            <span className="font-mono">{s.cluster_error}</span>
          </Callout>
        ) : null}
        {s.health === "NOT_FOUND" ? (
          <Callout tone="neutral" title="Not in the cluster">
            This workload no longer exists; its experiment history is kept below.
          </Callout>
        ) : null}
        {s.live ? (
          <DescriptionList
            items={[
              { label: "Health", value: <HealthBadge health={s.health} /> },
              { label: "Ready / desired", value: <Replicas ready={s.live.ready_pods} desired={s.live.desired_replicas} /> },
              { label: "Running pods", value: <span className="font-mono text-xs">{s.live.running_pods}</span> },
              {
                label: "Ready pods",
                value: s.live.ready_pod_names.length ? (
                  <ul className="grid gap-0.5 font-mono text-xs">
                    {s.live.ready_pod_names.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                ) : (
                  "None"
                ),
              },
            ]}
          />
        ) : null}
      </CardBody>
    </Card>
  );
}

function Resilience({ s }: { s: Detail }) {
  const latest = s.latest_score;
  return (
    <Card>
      <CardHeader title="Resilience" description="From this workload's experiments" />
      <CardBody>
        <DescriptionList
          items={[
            {
              label: "Latest score",
              value: latest ? (
                <span className="flex items-center gap-2">
                  <ScoreCell score={latest} />
                  {latest.rating ? <Badge>{latest.rating}</Badge> : null}
                  <Link href={`/reports/${latest.experiment_id}`} className="text-xs text-muted hover:text-accent">
                    {formatRelative(latest.at)}
                  </Link>
                </span>
              ) : (
                "Not scored yet"
              ),
            },
            { label: "Experiments", value: <span className="font-mono text-xs">{s.experiment_count}</span> },
          ]}
        />
      </CardBody>
    </Card>
  );
}

function Faults({ s }: { s: Detail }) {
  return (
    <Card>
      <CardHeader title="Tested faults" description="Per fault type and deletion mode" />
      <Table>
        <THead>
          <tr>
            <TH>Fault</TH>
            <TH className="text-right">Runs</TH>
            <TH className="text-right">Completed</TH>
            <TH className="text-right">Latest score</TH>
            <TH>Last run</TH>
          </tr>
        </THead>
        <TBody>
          {s.faults.map((f) => (
            <TR key={`${f.fault_type}-${f.pod_delete_mode}`}>
              <TD className="text-xs">
                {f.fault_type} <span className="text-faint">· {f.pod_delete_mode}</span>
              </TD>
              <TD className="text-right font-mono text-xs tabular-nums">{f.runs}</TD>
              <TD className="text-right font-mono text-xs tabular-nums">{f.completed}</TD>
              <TD className="text-right">
                {f.latest_score ? <ScoreCell score={f.latest_score} /> : <span className="text-faint">—</span>}
              </TD>
              <TD className="text-xs text-muted" title={formatDateTime(f.last_run_at)}>{formatRelative(f.last_run_at)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}

function Experiments({ s }: { s: Detail }) {
  const more = s.experiment_count - s.experiments.length;
  return (
    <Card>
      <CardHeader
        title="Recent experiments"
        description={more > 0 ? `Newest ${s.experiments.length} of ${s.experiment_count}` : undefined}
        actions={
          <ButtonLink href={`/experiments?ns=${encodeURIComponent(s.namespace)}&q=${encodeURIComponent(s.name)}`} size="sm" variant="ghost">
            In history
          </ButtonLink>
        }
      />
      <Table>
        <THead>
          <tr>
            <TH>Experiment</TH>
            <TH>Fault</TH>
            <TH>Outcome</TH>
            <TH className="text-right">Score</TH>
            <TH className="text-right">Recovery</TH>
            <TH>Created</TH>
          </tr>
        </THead>
        <TBody>
          {s.experiments.map((e) => (
            <TR key={e.id}>
              <TD>
                <Link href={`/experiments/${e.id}`} className="text-xs font-medium hover:text-accent">{e.name}</Link>
                <div className="font-mono text-2xs text-faint">{shortId(e.id)}</div>
              </TD>
              <TD className="text-xs">
                {e.fault_type} <span className="text-faint">· {e.pod_delete_mode} · {e.affected_replicas}×</span>
              </TD>
              <TD>
                <ExperimentStateBadge experiment={e} />
                {e.outcome_reason ? (
                  <div className="mt-0.5 max-w-72 truncate text-2xs text-faint" title={e.outcome_reason}>{e.outcome_reason}</div>
                ) : null}
              </TD>
              <TD className="text-right"><ScoreCell score={e.score} /></TD>
              <TD className="text-right font-mono text-xs tabular-nums">
                {e.time_to_recovery_seconds !== null ? formatSeconds(e.time_to_recovery_seconds) : <span className="text-faint">—</span>}
              </TD>
              <TD className="text-xs text-muted" title={formatDateTime(e.created_at)}>{formatRelative(e.created_at)}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}

export function ServiceDetailView({ namespace, kind, name }: { namespace: string; kind: string; name: string }) {
  const validKind = (WORKLOAD_KINDS as readonly string[]).includes(kind);
  const { data: s, isPending, isError, error, refetch } = useService(namespace, kind as WorkloadKind, name);
  const target = { namespace, kind, name };

  const header = (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <p className="text-2xs font-medium tracking-wide text-faint uppercase">{kind}</p>
        <h1 className="mt-1 flex items-center gap-3 font-mono text-xl font-semibold tracking-tight">
          {namespace}/{name}
          {s ? <HealthBadge health={s.health} /> : null}
        </h1>
      </div>
      {s && s.health !== "NOT_FOUND" ? (
        <ButtonLink href={newExperimentHref(target)} variant="primary">
          New experiment on this workload
        </ButtonLink>
      ) : null}
    </header>
  );

  if (!validKind)
    return (
      <Card>
        <EmptyState title="Unsupported workload kind" description={`Only ${WORKLOAD_KINDS.join(" and ")} are supported.`} action={<ButtonLink href="/services">All services</ButtonLink>} />
      </Card>
    );
  if (isPending) return <div className="grid gap-4">{header}<Card><LoadingState rows={6} label="Loading service" /></Card></div>;
  if (isError)
    return (
      <div className="grid gap-4">
        {header}
        <Card>
          {error instanceof ApiError && error.status === 404 ? (
            <EmptyState title="Service not found" description={error.detail} action={<ButtonLink href="/services">All services</ButtonLink>} />
          ) : (
            <ErrorState title="Could not load this service" message={error.message} onRetry={() => refetch()} />
          )}
        </Card>
      </div>
    );

  return (
    <div className="grid gap-4">
      {header}
      <div className="grid gap-4 lg:grid-cols-2">
        <KubernetesHealth s={s} />
        <Resilience s={s} />
      </div>
      {s.experiment_count === 0 ? (
        <Card>
          <EmptyState
            title="Not tested yet"
            description="No AutoResilience experiment has targeted this workload, so there is no score, fault coverage or history to show."
            action={
              <ButtonLink href={newExperimentHref(target)} variant="primary" size="sm">
                Run the first experiment
              </ButtonLink>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <ScoreTrend points={s.score_history} version={s.score_version} />
            <Faults s={s} />
          </div>
          <Experiments s={s} />
        </>
      )}
    </div>
  );
}
