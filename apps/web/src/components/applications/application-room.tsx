"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";

import { TopologyView } from "@/components/topology/topology-view";
import { Button, ButtonLink } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";
import { InfoHint } from "@/components/ui/info-hint";
import { PageHeader } from "@/components/ui/page-header";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { ApiError, api } from "@/lib/api/client";
import { queryKeys, useApplication, useApplicationTopology } from "@/lib/api/queries";
import type { Application } from "@/lib/api/types";
import { TOUR_TARGET } from "@/lib/help-content";
import { importHref } from "@/lib/imports";

import { ClusterRoleBadge, contextLabel } from "./cluster-badge";

function ForgetControl({ application }: { application: Application }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const router = useRouter();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteApplication(application.id);
      queryClient.removeQueries({ queryKey: queryKeys.application(application.id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications });
      router.push("/applications");
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.detail}` : String(e));
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant="ghost" onClick={() => dialogRef.current?.showModal()}>
        Forget application
      </Button>
      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        className="m-auto w-full max-w-md rounded-lg border border-line-strong bg-surface p-0 text-fg backdrop:bg-black/60"
      >
        <div className="grid gap-4 p-5">
          <div>
            <h2 id={titleId} className="text-base font-semibold">
              Forget “{application.name}”?
            </h2>
            <p className="mt-1 text-xs text-muted">
              Only this console view is removed. Nothing in the cluster changes, and experiments on its workloads stay in
              the history.
            </p>
          </div>
          {error ? (
            <Callout tone="danger" title="Not removed" role="alert">
              <span className="font-mono">{error}</span>
            </Callout>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => dialogRef.current?.close()} disabled={busy}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => void confirm()} disabled={busy}>
              {busy ? "Removing…" : "Forget application"}
            </Button>
          </div>
        </div>
      </dialog>
    </>
  );
}

export function ApplicationRoom({ id }: { id: string }) {
  const app = useApplication(id);
  const authorized = !!app.data?.cluster;
  const topology = useApplicationTopology(id, authorized);

  if (app.isPending) return <Card><LoadingState rows={4} label="Loading application" /></Card>;
  if (app.isError) {
    const missing = app.error instanceof ApiError && app.error.status === 404;
    return (
      <Card>
        <ErrorState
          title={missing ? "Application not found" : "Could not load the application"}
          message={missing ? "It may have been forgotten in another tab." : app.error.message}
          onRetry={missing ? undefined : () => app.refetch()}
        />
      </Card>
    );
  }
  const a = app.data;

  return (
    <>
      <PageHeader
        title={a.name}
        description={`Topology of ${a.namespaces.join(", ")} in ${contextLabel(a.context)}, read from the cluster now.`}
        meta={
          <span className="inline-flex items-center gap-1.5" data-tour={TOUR_TARGET.topologyCluster}>
            <ClusterRoleBadge cluster={a.cluster} />
            <InfoHint label="cluster roles">
              <strong className="text-fg">Execution cluster</strong>: the engine&apos;s <code>KUBE_CONTEXT</code>; experiments may run
              here after safety validation. <strong className="text-fg">Read-only discovery</strong>: granted with{" "}
              <code>ar cluster import</code>; topology only, never chaos.
            </InfoHint>
          </span>
        }
        actions={
          topology.data?.imported ? (
            <ButtonLink href={importHref(topology.data.imported.import_id)} variant="ghost">
              Managed by import {topology.data.imported.name}
            </ButtonLink>
          ) : (
            <ForgetControl application={a} />
          )
        }
      />
      {!a.cluster ? (
        <Callout tone="warning" title="This cluster is no longer authorized for the engine" role="status">
          The context <code className="font-mono">{contextLabel(a.context)}</code> or one of its namespaces was removed from
          the engine&apos;s configuration (<code className="font-mono">ar cluster remove</code> or a changed{" "}
          <code className="font-mono">KUBE_CONTEXT</code>), so nothing is read. Import it again or{" "}
          <ButtonLink href="/applications/new" size="sm" variant="ghost">
            onboard it again
          </ButtonLink>
          .
        </Callout>
      ) : topology.isPending ? (
        <Card><LoadingState rows={6} label="Reading the topology" /></Card>
      ) : topology.data ? (
        <TopologyView
          topology={topology.data}
          refreshError={topology.isError ? topology.error.message : null}
          refreshing={topology.isFetching}
          onRefresh={() => void topology.refetch()}
        />
      ) : (
        <Card>
          <ErrorState title="Could not read the topology" message={topology.error?.message} onRetry={() => topology.refetch()} />
        </Card>
      )}
    </>
  );
}
