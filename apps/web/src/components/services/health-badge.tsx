import { Badge } from "@/components/ui/badge";
import type { WorkloadHealth } from "@/lib/api/types";
import { HEALTH_META } from "@/lib/workload-health";

export function HealthBadge({ health }: { health: WorkloadHealth }) {
  const meta = HEALTH_META[health];
  return (
    <Badge tone={meta.tone} dot title={meta.description}>
      {meta.label}
    </Badge>
  );
}

/** Ready / desired as the controller reports it, e.g. "2/3". */
export function Replicas({ ready, desired }: { ready: number; desired: number }) {
  return (
    <span className="font-mono text-xs tabular-nums">
      <span className={ready < desired ? "text-warning" : undefined}>{ready}</span>
      <span className="text-faint">/{desired}</span>
    </span>
  );
}

export function serviceHref(s: { namespace: string; kind: string; name: string }) {
  return `/services/${encodeURIComponent(s.namespace)}/${s.kind}/${encodeURIComponent(s.name)}`;
}

export function newExperimentHref(s: { namespace: string; kind: string; name: string }) {
  const params = new URLSearchParams({ namespace: s.namespace, kind: s.kind, name: s.name });
  return `/experiments/new?${params}`;
}
