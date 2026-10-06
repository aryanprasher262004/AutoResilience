import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/states";
import type { Experiment } from "@/lib/api/types";
import type { OrchestrationView } from "@/lib/evidence";
import { formatClock, formatDateTime } from "@/lib/format";

import { milestones } from "./impact-recovery";

export function EventsTab({ experiment: e, orch }: { experiment: Experiment; orch: OrchestrationView }) {
  const points = milestones(e, orch);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Evidence timeline" description="Recorded timestamps only, in order (UTC)" />
        <ol className="divide-y divide-line">
          {points.map((m, i) => (
            <li key={`${m.at}-${i}`} className="grid grid-cols-[6.5rem_1fr] gap-3 px-4 py-2 text-xs">
              <span className="font-mono text-faint" title={formatDateTime(m.at)}>
                {formatClock(m.at)}
              </span>
              <span>
                <Badge tone={m.tone} dot>
                  {m.label}
                </Badge>
                {m.detail ? <span className="ml-2 font-mono text-2xs text-muted">{m.detail}</span> : null}
              </span>
            </li>
          ))}
        </ol>
      </Card>
      <Card>
        <CardHeader
          title="Orchestration log"
          description={orch.mode === "auto" ? "Events written by the orchestrator" : "Manually driven: no orchestrator events"}
        />
        {orch.events.length ? (
          <ol className="divide-y divide-line">
            {orch.events.map((ev, i) => (
              <li key={`${ev.at}-${i}`} className="grid grid-cols-[6.5rem_1fr] gap-3 px-4 py-2 text-xs">
                <span className="font-mono text-faint" title={formatDateTime(ev.at)}>
                  {formatClock(ev.at)}
                </span>
                <span className="text-muted">{ev.text}</span>
              </li>
            ))}
          </ol>
        ) : (
          <EmptyState title="No orchestration events" description="This experiment was not started with Run." />
        )}
      </Card>
    </div>
  );
}
