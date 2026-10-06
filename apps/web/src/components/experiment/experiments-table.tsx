"use client";

import Link from "next/link";

import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { useExperiments } from "@/lib/api/queries";
import { formatDateTime, formatRelative, shortId } from "@/lib/format";

import { ScoreCell } from "./score-cell";
import { StateBadge } from "./state-badge";

export function ExperimentsTable() {
  const { data, isPending, isError, error, refetch } = useExperiments();

  return (
    <Card>
      {isPending ? (
        <LoadingState rows={5} label="Loading experiments" />
      ) : isError ? (
        <ErrorState message={error.message} onRetry={() => refetch()} />
      ) : data.length === 0 ? (
        <EmptyState
          title="No experiments yet"
          description="Experiments you create through the API or the experiment builder appear here with their live state."
          action={
            <ButtonLink href="/experiments/new" variant="primary" size="sm">
              New Experiment
            </ButtonLink>
          }
        />
      ) : (
        <Table>
          <THead>
            <tr>
              <TH>Experiment</TH>
              <TH>Target</TH>
              <TH>Fault</TH>
              <TH>State</TH>
              <TH className="text-right">Score</TH>
              <TH>Created</TH>
            </tr>
          </THead>
          <TBody>
            {data.map((e) => (
              <TR key={e.id}>
                <TD>
                  <Link href={`/experiments/${e.id}`} className="font-medium hover:text-accent">
                    {e.name}
                  </Link>
                  <div className="font-mono text-2xs text-faint" title={e.id}>
                    {shortId(e.id)}
                  </div>
                </TD>
                <TD className="font-mono text-xs">
                  {e.target.namespace}/{e.target.name}
                  <div className="font-sans text-2xs text-faint">{e.target.kind}</div>
                </TD>
                <TD className="text-xs">
                  {e.fault_type}
                  <div className="text-2xs text-faint">
                    {e.pod_delete_mode} · {e.affected_replicas} replica
                    {e.affected_replicas === 1 ? "" : "s"} · {e.duration_seconds}s
                  </div>
                </TD>
                <TD>
                  <StateBadge state={e.state} />
                </TD>
                <TD className="text-right">
                  <ScoreCell score={e.score} />
                </TD>
                <TD className="text-xs text-muted" title={formatDateTime(e.created_at)}>
                  {formatRelative(e.created_at)}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </Card>
  );
}
