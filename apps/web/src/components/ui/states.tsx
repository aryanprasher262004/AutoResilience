import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

import { Button } from "./button";

function Frame({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-12 text-center",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Frame>
      <p className="text-sm font-medium text-fg">{title}</p>
      {description ? <p className="max-w-md text-xs text-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </Frame>
  );
}

/** Skeleton rows; `label` is announced to assistive tech. */
export function LoadingState({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-2 px-4 py-4">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-6 animate-pulse rounded bg-surface-2" />
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}

export function ErrorState({
  title = "Could not load data",
  message,
  onRetry,
}: {
  title?: ReactNode;
  message?: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <Frame>
      <p className="text-sm font-medium text-danger">{title}</p>
      {message ? <p className="max-w-md font-mono text-xs text-muted">{message}</p> : null}
      {onRetry ? (
        <Button size="sm" className="mt-2" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </Frame>
  );
}

/** Honest placeholder for an area that is not built yet. No sample data. */
export function PlannedState({
  milestone,
  title,
  children,
}: {
  milestone: string;
  title: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-line-strong px-6 py-10">
      <p className="text-2xs font-medium tracking-wide text-faint uppercase">{milestone}</p>
      <p className="mt-1 text-sm font-medium text-fg">{title}</p>
      <div className="mt-2 max-w-2xl space-y-2 text-xs leading-relaxed text-muted">{children}</div>
    </div>
  );
}
