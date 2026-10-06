"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { ApiError } from "@/lib/api/client";
import { queryKeys, useReadiness } from "@/lib/api/queries";
import type { ReadinessReason } from "@/lib/api/types";
import { cn } from "@/lib/cn";

type State = "checking" | "ready" | "not_ready" | "unreachable";

const NOT_READY: Record<ReadinessReason, string> = {
  database_unreachable: "Database unavailable",
  schema_missing: "Database not migrated",
  schema_outdated: "Database schema outdated",
};

/**
 * API status from GET /ready, polled. "Ready" only when the API answers *and* its
 * required dependencies pass; a live process with a broken database is "not ready".
 */
export function ApiStatus({ compact = false, detailed = false }: { compact?: boolean; detailed?: boolean }) {
  const { data, error, isPending } = useReadiness();
  const queryClient = useQueryClient();

  const failed = data?.checks.find((c) => c.status === "fail");
  let state: State;
  let label: string;
  let detail: string | undefined;
  if (isPending) [state, label] = ["checking", "Checking API"];
  else if (data?.status === "ready") [state, label, detail] = ["ready", "API ready", data.checks.map((c) => c.detail).join("; ")];
  else if (data) [state, label, detail] = ["not_ready", failed?.reason ? NOT_READY[failed.reason] : "API not ready", failed?.detail];
  else if (error instanceof ApiError && !error.unavailable)
    // Answered, but not with a readiness result (e.g. an API without /ready).
    [state, label, detail] = ["not_ready", "API not ready", error.message];
  else [state, label, detail] = ["unreachable", "API unreachable", error?.message];

  // When the backend becomes ready again, refetch data that failed while it was not.
  const previous = useRef<State>(state);
  useEffect(() => {
    if (state === "ready" && (previous.current === "not_ready" || previous.current === "unreachable")) {
      void queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== queryKeys.readiness[0] });
    }
    previous.current = state;
  }, [state, queryClient]);

  return (
    <span className={cn("inline-flex flex-col gap-0.5", compact ? "" : "text-muted")}>
      <span title={detail ? `${label}: ${detail}` : label} className="inline-flex items-center gap-2 text-xs">
        <span
          aria-hidden
          className={cn(
            "size-2 shrink-0 rounded-full",
            state === "ready" && "bg-success",
            state === "not_ready" && "bg-warning",
            state === "unreachable" && "bg-danger",
            state === "checking" && "bg-faint",
          )}
        />
        <span role="status" className={compact ? "sr-only" : ""}>
          {label}
        </span>
      </span>
      {detailed && detail ? <span className="font-mono text-2xs break-all text-faint">{detail}</span> : null}
    </span>
  );
}
