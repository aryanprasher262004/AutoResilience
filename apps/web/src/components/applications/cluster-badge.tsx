import { Badge } from "@/components/ui/badge";
import type { ClusterRef } from "@/lib/api/types";

export function contextLabel(context: string | null): string {
  return context ?? "current kubeconfig context";
}

/** Execution: experiments may run there (after safety validation). Discovery: read-only. */
export function ClusterRoleBadge({ cluster }: { cluster: ClusterRef | null }) {
  if (!cluster) {
    return (
      <Badge tone="danger" dot title="The context or its namespaces are no longer configured for this engine">
        No longer authorized
      </Badge>
    );
  }
  return cluster.role === "execution" ? (
    <Badge tone="info" dot title="The engine's KUBE_CONTEXT: experiments run here, after safety validation">
      Execution cluster
    </Badge>
  ) : (
    <Badge tone="neutral" dot title="Read-only discovery: no chaos execution is granted on this cluster">
      Read-only discovery
    </Badge>
  );
}
