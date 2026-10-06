"use client";

import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DescriptionList } from "@/components/ui/description-list";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Tabs } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api/client";
import { useExperiment } from "@/lib/api/queries";
import type { Experiment } from "@/lib/api/types";
import { presentState } from "@/lib/experiment-state";
import { formatDateTime } from "@/lib/format";

import { ScoreCell } from "./score-cell";
import { ExperimentStateBadge } from "./state-badge";

/** Why the experiment ended where it did, from whichever stage decided it. */
function outcomeReason(e: Experiment): string | null {
  const orchestration = e.orchestration as { result?: { reason?: string } } | null;
  return (
    e.observation?.result.reason ??
    orchestration?.result?.reason ??
    e.chaos?.failure_reason ??
    (e.validation_result && !e.validation_result.passed
      ? [...e.validation_result.static_checks, ...e.validation_result.cluster_checks]
          .filter((c) => c.status !== "PASSED")
          .map((c) => c.message)
          .join("; ")
      : null)
  );
}

export function ExperimentSummary({ id }: { id: string }) {
  const { data: e, isPending, isError, error, refetch } = useExperiment(id);

  if (isPending) {
    return (
      <Card>
        <LoadingState rows={6} label="Loading experiment" />
      </Card>
    );
  }
  if (isError) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <Card>
        {notFound ? (
          <EmptyState
            title="Experiment not found"
            description={`No experiment with id ${id} exists in this backend.`}
            action={<ButtonLink href="/experiments">Back to experiments</ButtonLink>}
          />
        ) : (
          <ErrorState message={error.message} onRetry={() => refetch()} />
        )}
      </Card>
    );
  }

  const reason = outcomeReason(e);
  return (
    <>
      <PageHeader
        title={e.name}
        description={presentState(e).description}
        meta={
          <>
            <ExperimentStateBadge experiment={e} />
            <span className="font-mono text-xs text-faint">{e.id}</span>
          </>
        }
      />
      <Tabs
        items={[
          {
            id: "summary",
            label: "Summary",
            content: (
              <div className="grid gap-4">
                <Card>
                  <CardHeader title="Experiment" />
                  <CardBody>
                    <DescriptionList
                      items={[
                        {
                          label: "Target",
                          value: (
                            <span className="font-mono text-xs">
                              {e.target.kind} {e.target.namespace}/{e.target.name}
                            </span>
                          ),
                        },
                        {
                          label: "Fault",
                          value: `${e.fault_type} · ${e.pod_delete_mode}`,
                        },
                        {
                          label: "Blast radius",
                          value: `${e.affected_replicas} replica(s) for ${e.duration_seconds}s`,
                        },
                        {
                          label: "Safety policy",
                          value:
                            (e.validation_result?.policy as { name?: string } | undefined)
                              ?.name ?? "Not validated yet",
                        },
                        { label: "Created", value: formatDateTime(e.created_at) },
                        { label: "Last update", value: formatDateTime(e.updated_at) },
                        { label: "Resilience score", value: <ScoreCell score={e.score} /> },
                        {
                          label: "Orchestration",
                          value:
                            (e.orchestration as { mode?: string } | null)?.mode ?? "Manual",
                        },
                        {
                          label: "ChaosEngine",
                          value: (
                            <span className="font-mono text-xs">
                              {e.chaos?.engine_name ?? "—"}
                            </span>
                          ),
                        },
                      ]}
                    />
                    {reason ? (
                      <p className="mt-4 border-t border-line pt-3 text-xs text-muted">
                        <span className="font-medium text-fg">Outcome: </span>
                        {reason}
                      </p>
                    ) : null}
                  </CardBody>
                </Card>
                <p className="text-xs text-faint">
                  The live experiment view (timeline, evidence and score breakdown) is the next
                  frontend milestone. All recorded evidence is available under “Raw evidence”.
                </p>
              </div>
            ),
          },
          {
            id: "raw",
            label: "Raw evidence",
            content: (
              <Card>
                <CardHeader
                  title="API response"
                  description={`GET /experiments/${e.id}, exactly as returned by the backend`}
                />
                <pre className="max-h-[60vh] overflow-auto px-4 py-3 font-mono text-xs leading-relaxed text-muted">
                  {JSON.stringify(e, null, 2)}
                </pre>
              </Card>
            ),
          },
        ]}
      />
    </>
  );
}
