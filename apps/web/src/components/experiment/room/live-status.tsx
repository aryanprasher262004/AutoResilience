import type { ReactNode } from "react";

import type { Experiment } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import type { OrchestrationView } from "@/lib/evidence";
import { readLitmus } from "@/lib/evidence";
import { presentState } from "@/lib/experiment-state";
import { formatClock, formatDateTime, formatRelative } from "@/lib/format";

import { ExperimentStateBadge } from "../state-badge";

function Cell({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0 px-4 py-3", className)}>
      <p className="text-2xs font-medium tracking-wide text-faint uppercase">{label}</p>
      <div className="mt-1 text-sm text-fg">{children}</div>
    </div>
  );
}

/** What is happening right now, from the latest API response. */
export function LiveStatus({
  experiment: e,
  orch,
  active,
  fetchedAt,
  fetching,
}: {
  experiment: Experiment;
  orch: OrchestrationView;
  active: boolean;
  fetchedAt: number;
  fetching: boolean;
}) {
  const latest = orch.events.at(-1) ?? null;
  const error = orch.lastError ?? e.observation?.last_error ?? readLitmus(e)?.lastError ?? null;
  return (
    <section
      aria-label="Live status"
      className="grid divide-y divide-line rounded-lg border border-line bg-surface md:grid-cols-[1.1fr_1.6fr_1fr] md:divide-x md:divide-y-0"
    >
      <Cell label="Current state">
        <div className="flex items-center gap-2">
          <ExperimentStateBadge experiment={e} />
        </div>
        <p className="mt-1 truncate text-xs text-muted">{presentState(e).description}</p>
      </Cell>
      <Cell label={orch.mode === "auto" ? "Latest orchestration event" : "Latest event"}>
        {latest ? (
          <>
            <p className="truncate text-xs" title={latest.text}>
              {latest.text}
            </p>
            <p className="mt-0.5 font-mono text-2xs text-faint">{formatClock(latest.at)} UTC</p>
          </>
        ) : (
          <p className="text-xs text-faint">No orchestration events (manually driven experiment)</p>
        )}
        {error ? (
          <p className="mt-1 truncate text-xs text-warning" title={error}>
            Last error: {error}
          </p>
        ) : null}
      </Cell>
      <Cell label="Updates">
        <p className="text-xs" title={formatDateTime(e.updated_at)}>
          Changed {formatRelative(e.updated_at)}
        </p>
        <p className="mt-0.5 flex items-center gap-1.5 text-2xs text-faint">
          <span
            aria-hidden
            className={cn("size-1.5 rounded-full", active ? (fetching ? "bg-info" : "bg-info/60") : "bg-faint")}
          />
          {active ? `Live · polling every 3 s · checked ${formatRelative(new Date(fetchedAt).toISOString())}` : "Final state · polling stopped"}
        </p>
      </Cell>
    </section>
  );
}
