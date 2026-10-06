import { Card, CardBody, CardHeader } from "@/components/ui/card";
import type { Experiment, ExperimentState } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import type { OrchestrationView } from "@/lib/evidence";
import { STATE_META, presentState } from "@/lib/experiment-state";
import { formatClock, formatSeconds, secondsBetween } from "@/lib/format";

type StepStatus = "done" | "current" | "waiting" | "pending" | "failed" | "aborted" | "undetermined" | "skipped";

const STAGES: ExperimentState[] = ["CREATED", "VALIDATING", "BASELINING", "INJECTING", "OBSERVING", "RECOVERING"];

/** Stage at which a terminal non-success run stopped, and whether that is recorded or inferred. */
function stoppedAt(e: Experiment, orch: OrchestrationView): { stage: ExperimentState; inferred: boolean } | null {
  if (e.state === "VALIDATION_FAILED") return { stage: "VALIDATING", inferred: false };
  if (e.state === "INJECTION_FAILED") return { stage: "INJECTING", inferred: false };
  if (e.state !== "ABORTED" && e.state !== "UNKNOWN") return null;
  // Recorded by the orchestrator, e.g. "OBSERVING -> ABORTED (...)".
  for (const ev of [...orch.events].reverse()) {
    const m = ev.text.match(/^([A-Z_]+) -> (ABORTED|UNKNOWN)\b/);
    if (m && STAGES.includes(m[1] as ExperimentState)) return { stage: m[1] as ExperimentState, inferred: false };
  }
  // Otherwise the furthest stage that left evidence behind.
  const stage: ExperimentState = e.observation?.recovery
    ? "RECOVERING"
    : e.observation
      ? "OBSERVING"
      : e.chaos?.engine_name
        ? "INJECTING"
        : e.baseline
          ? "BASELINING"
          : e.validation_result
            ? "VALIDATING"
            : "CREATED";
  return { stage, inferred: true };
}

function statuses(e: Experiment, orch: OrchestrationView) {
  const stop = stoppedAt(e, orch);
  const waiting = presentState(e).label === "Validated · not started";
  return {
    stop,
    stage: (s: ExperimentState): StepStatus => {
      const i = STAGES.indexOf(s);
      if (e.state === "COMPLETED") return "done";
      if (stop) {
        const at = STAGES.indexOf(stop.stage);
        if (i < at) return "done";
        if (i > at) return "skipped";
        return e.state === "ABORTED" ? "aborted" : e.state === "UNKNOWN" ? "undetermined" : "failed";
      }
      const current = STAGES.indexOf(e.state);
      if (i < current) return "done";
      if (i === current) return waiting ? "waiting" : "current";
      return "pending";
    },
  };
}

const DOT: Record<StepStatus, string> = {
  done: "bg-success/15 text-success ring-success/40",
  current: "bg-accent text-white ring-accent",
  waiting: "bg-surface-3 text-muted ring-line-strong",
  pending: "text-faint ring-line-strong",
  failed: "bg-danger/15 text-danger ring-danger/50",
  aborted: "bg-surface-3 text-fg ring-faint",
  undetermined: "bg-warning/15 text-warning ring-warning/50",
  skipped: "text-faint/60 ring-line",
};

const GLYPH: Partial<Record<StepStatus, string>> = { done: "✓", failed: "✕", aborted: "■", undetermined: "?" };

const STATUS_TEXT: Record<StepStatus, string> = {
  done: "completed",
  current: "in progress",
  waiting: "waiting to be run",
  pending: "pending",
  failed: "failed here",
  aborted: "aborted here",
  undetermined: "outcome undetermined here",
  skipped: "not reached",
};

function Step({
  index,
  label,
  status,
  at,
  took,
  last,
}: {
  index: number;
  label: string;
  status: StepStatus;
  at: string | null;
  took: number | null;
  last: boolean;
}) {
  return (
    <li className="relative flex min-w-28 flex-1 flex-col gap-1.5">
      {!last ? (
        <span
          aria-hidden
          className={cn(
            "absolute top-2.5 left-6 h-px w-[calc(100%-1.5rem)]",
            status === "done" ? "bg-success/40" : "bg-line-strong",
          )}
        />
      ) : null}
      <span
        aria-hidden
        className={cn(
          "relative z-10 flex size-5 items-center justify-center rounded-full font-mono text-2xs ring-1",
          DOT[status],
        )}
      >
        {GLYPH[status] ?? index + 1}
      </span>
      <span
        className={cn(
          "text-xs font-medium",
          status === "current" ? "text-fg" : status === "pending" || status === "skipped" ? "text-faint" : "text-muted",
        )}
        aria-current={status === "current" ? "step" : undefined}
      >
        {label}
        <span className="sr-only"> ({STATUS_TEXT[status]})</span>
      </span>
      <span className="font-mono text-2xs text-faint">
        {at ? formatClock(at) : status === "skipped" ? "not reached" : " "}
        {took !== null ? ` · ${formatSeconds(took)}` : ""}
      </span>
    </li>
  );
}

export function Lifecycle({ experiment: e, orch }: { experiment: Experiment; orch: OrchestrationView }) {
  const { stop, stage } = statuses(e, orch);
  const since = orch.stateSince;
  // Only recorded timestamps; CREATED falls back to the experiment's creation time.
  const enteredAt = (s: ExperimentState): string | null => since[s] ?? (s === "CREATED" ? e.created_at : null);
  const finalState = STATE_META[e.state].terminal ? e.state : null;
  const finalLabel = finalState ? STATE_META[finalState].label : "Completed";
  const finalStatus: StepStatus =
    e.state === "COMPLETED" ? "done" : finalState ? (e.state === "ABORTED" ? "aborted" : e.state === "UNKNOWN" ? "undetermined" : "failed") : "pending";

  return (
    <Card>
      <CardHeader
        title="Lifecycle"
        description={
          orch.mode === "auto"
            ? "Stage entry times recorded by the orchestrator (UTC)"
            : "Manually driven experiment: only the creation time is recorded per stage"
        }
      />
      <CardBody>
        <ol className="flex gap-2 overflow-x-auto pb-1" aria-label="Experiment lifecycle">
          {STAGES.map((s, i) => {
            const next = STAGES[i + 1];
            const took = next ? secondsBetween(enteredAt(s), enteredAt(next)) : null;
            return (
              <Step
                key={s}
                index={i}
                label={STATE_META[s].label}
                status={stage(s)}
                at={enteredAt(s)}
                took={stage(s) === "done" ? took : null}
                last={false}
              />
            );
          })}
          <Step
            index={STAGES.length}
            label={finalLabel}
            status={finalStatus}
            at={finalState ? (since[finalState] ?? null) : null}
            took={null}
            last
          />
        </ol>
        {stop?.inferred ? (
          <p className="mt-2 text-2xs text-faint">
            Stopping stage inferred from the evidence recorded before {STATE_META[e.state].label.toLowerCase()} (no
            orchestration events for this experiment).
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
