import { cn } from "@/lib/cn";

export type Step = { id: string; label: string };

/** Ordered progress indicator; the current step is announced with aria-current. */
export function Stepper({ steps, current }: { steps: Step[]; current: string }) {
  const index = steps.findIndex((s) => s.id === current);
  return (
    <ol className="flex flex-wrap items-center gap-2 text-xs" aria-label="Progress">
      {steps.map((step, i) => {
        const done = i < index;
        const active = i === index;
        return (
          <li key={step.id} className="flex items-center gap-2">
            {i > 0 ? <span aria-hidden className="h-px w-6 bg-line-strong" /> : null}
            <span
              aria-current={active ? "step" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1",
                active && "bg-surface-3 text-fg",
                !active && done && "text-muted",
                !active && !done && "text-faint",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "flex size-5 items-center justify-center rounded-full font-mono text-2xs ring-1",
                  active && "bg-accent text-white ring-accent",
                  done && "bg-success/15 text-success ring-success/40",
                  !active && !done && "ring-line-strong",
                )}
              >
                {done ? "✓" : i + 1}
              </span>
              <span className="font-medium">{step.label}</span>
              {done ? <span className="sr-only">(completed)</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
