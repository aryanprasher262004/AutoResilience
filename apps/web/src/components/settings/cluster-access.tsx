"use client";

import { ClusterRoleBadge, contextLabel } from "@/components/applications/cluster-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { useClusters } from "@/lib/api/queries";
import { TOUR_TARGET } from "@/lib/help-content";

const AR = "python3 tools/ar/ar.py";

/** The clusters the engine was started with (GET /clusters, no cluster contacted). Read-only. */
export function ClusterAccess() {
  const { data, isPending, isError, error, refetch } = useClusters();
  return (
    <Card data-tour={TOUR_TARGET.settingsAccess}>
      <CardHeader
        level={3}
        title="Kubernetes access"
        description="Which clusters the engine may read, and where experiments may run. Fixed when the engine starts."
      />
      {isPending ? (
        <LoadingState rows={2} label="Loading clusters" />
      ) : isError ? (
        <ErrorState title="Could not load clusters" message={error.message} onRetry={() => refetch()} />
      ) : (
        <ul className="divide-y divide-line" aria-label="Authorized clusters">
          {data.items.map((c) => (
            <li key={c.context ?? ""} className="grid gap-1.5 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-sm text-fg">{contextLabel(c.context)}</span>
                <span className="flex flex-wrap gap-1.5">
                  <ClusterRoleBadge cluster={c} />
                  <Badge tone={c.chaos_permitted ? "warning" : "neutral"}>
                    {c.chaos_permitted ? "Experiments allowed" : "No experiments"}
                  </Badge>
                </span>
              </div>
              <p className="text-xs text-muted">
                {c.role === "execution"
                  ? "Every namespace outside the system namespaces. The engine reads workloads and topology here and creates only its own ChaosEngines, after safety validation."
                  : `Read-only, limited to ${c.namespaces?.join(", ")}, with a ServiceAccount that can only list and read there.`}
              </p>
            </li>
          ))}
        </ul>
      )}
      <CardBody className="grid gap-1.5 border-t border-line text-xs leading-relaxed text-muted [&_code]:font-mono [&_code]:text-fg">
        <p>
          Changing access is terminal-only, so this browser can never widen it. Grant read-only discovery with{" "}
          <code>{AR} cluster import --context NAME --namespace NS</code> (shows its plan and asks first), revoke it with{" "}
          <code>{AR} cluster remove --context NAME</code>. The execution cluster is the engine&apos;s{" "}
          <code>KUBE_CONTEXT</code>; <code>{AR} install</code> re-grants its read access when it changes.
        </p>
        <p>The engine can never read Secrets or ConfigMaps, on any cluster.</p>
      </CardBody>
    </Card>
  );
}
