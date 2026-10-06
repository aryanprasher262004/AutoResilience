import { Badge } from "@/components/ui/badge";
import type { Experiment, ExperimentState } from "@/lib/api/types";
import { STATE_META, presentState } from "@/lib/experiment-state";

export function StateBadge({ state }: { state: ExperimentState }) {
  const meta = STATE_META[state];
  return (
    <Badge tone={meta.tone} dot title={`${state}: ${meta.description}`}>
      {meta.label}
    </Badge>
  );
}

/** Badge for a concrete experiment (accounts for validated-but-not-started). */
export function ExperimentStateBadge({ experiment }: { experiment: Experiment }) {
  const meta = presentState(experiment);
  return (
    <Badge tone={meta.tone} dot title={`${meta.state}: ${meta.description}`}>
      {meta.label}
    </Badge>
  );
}
