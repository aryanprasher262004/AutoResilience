import { Badge } from "@/components/ui/badge";
import type { ExperimentState } from "@/lib/api/types";
import { STATE_META } from "@/lib/experiment-state";

export function StateBadge({ state }: { state: ExperimentState }) {
  const meta = STATE_META[state];
  return (
    <Badge tone={meta.tone} dot title={`${state}: ${meta.description}`}>
      {meta.label}
    </Badge>
  );
}
