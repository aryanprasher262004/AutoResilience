"use client";

import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Tabs } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api/client";
import { useExperiment } from "@/lib/api/queries";
import { readOrchestration } from "@/lib/evidence";
import { isTerminal } from "@/lib/experiment-state";
import { formatDateTime } from "@/lib/format";

import { ExperimentStateBadge } from "../state-badge";
import { AbortControl } from "./abort-dialog";
import { EventsTab } from "./events-tab";
import { EvidenceTab } from "./evidence-tab";
import { ImpactRecovery } from "./impact-recovery";
import { Lifecycle } from "./lifecycle";
import { LiveStatus } from "./live-status";
import { MetricsTable } from "./metrics-table";
import { OutcomeBanner } from "./outcome-banner";
import { ScorePanel } from "./score-panel";

/** /experiments/[id]: the live experiment workspace. Everything shown comes from the API. */
export function ExperimentRoom({ id }: { id: string }) {
  const { data: e, isPending, isError, error, refetch, dataUpdatedAt, isFetching } = useExperiment(id);

  if (isPending) {
    return (
      <Card>
        <LoadingState rows={8} label="Loading experiment" />
      </Card>
    );
  }
  if (isError) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <Card>
          <EmptyState
            title="Experiment not found"
            description={`No experiment with id ${id} exists in this backend.`}
            action={<ButtonLink href="/experiments">Back to experiments</ButtonLink>}
          />
        </Card>
      );
    }
    return (
      <Card>
        <ErrorState title="Could not load this experiment" message={error.message} onRetry={() => refetch()} />
      </Card>
    );
  }

  const orch = readOrchestration(e);
  const active = !isTerminal(e.state);
  const target = `${e.target.kind} ${e.target.namespace}/${e.target.name}`;
  return (
    <div className="grid gap-4">
      <PageHeader
        title={e.name}
        description={e.description ?? undefined}
        meta={
          <>
            <ExperimentStateBadge experiment={e} />
            <span className="font-mono text-xs text-muted">{target}</span>
            <span className="text-xs text-faint">·</span>
            <span className="text-xs text-muted">
              {e.fault_type} · {e.pod_delete_mode} · {e.affected_replicas} replica{e.affected_replicas === 1 ? "" : "s"} ·{" "}
              {e.duration_seconds}s
            </span>
            <span className="text-xs text-faint">·</span>
            <span className="text-xs text-muted" title={orch.requestedAt ? formatDateTime(orch.requestedAt) : undefined}>
              {orch.requestedAt ? `Started ${formatDateTime(orch.requestedAt)}` : `Created ${formatDateTime(e.created_at)}`}
            </span>
          </>
        }
        actions={<AbortControl experiment={e} />}
      />
      <OutcomeBanner experiment={e} orch={orch} />
      <LiveStatus experiment={e} orch={orch} active={active} fetchedAt={dataUpdatedAt} fetching={isFetching} />
      <Tabs
        items={[
          {
            id: "overview",
            label: "Overview",
            content: (
              <div className="grid gap-4">
                <Lifecycle experiment={e} orch={orch} />
                <ImpactRecovery experiment={e} />
                <ScorePanel experiment={e} />
              </div>
            ),
          },
          { id: "metrics", label: "Metrics", content: <MetricsTable experiment={e} /> },
          {
            id: "events",
            label: `Events${orch.events.length ? ` (${orch.events.length})` : ""}`,
            content: <EventsTab experiment={e} orch={orch} />,
          },
          { id: "evidence", label: "Evidence", content: <EvidenceTab experiment={e} orch={orch} /> },
        ]}
      />
      <p className="font-mono text-2xs text-faint">id {e.id} · updated {formatDateTime(e.updated_at)}</p>
    </div>
  );
}
