"use client";

import { useHealth } from "@/lib/api/queries";
import { cn } from "@/lib/cn";

/** Real backend reachability (GET /health), polled; never assumed. */
export function ApiStatus({ compact = false }: { compact?: boolean }) {
  const { data, isPending, isError } = useHealth();
  const state = isPending ? "checking" : isError || data?.status !== "ok" ? "down" : "up";
  const label = { checking: "Checking API", up: "API connected", down: "API unreachable" }[state];
  return (
    <span
      title={label}
      className={cn("inline-flex items-center gap-2 text-xs", compact ? "" : "text-muted")}
    >
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          state === "up" && "bg-success",
          state === "down" && "bg-danger",
          state === "checking" && "bg-faint",
        )}
      />
      <span className={compact ? "sr-only" : ""}>{label}</span>
    </span>
  );
}
