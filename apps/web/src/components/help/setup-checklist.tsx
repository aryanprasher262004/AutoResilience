"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { ApiError } from "@/lib/api/client";
import { useDashboardSummary, useReadiness, useServices } from "@/lib/api/queries";

type Item = { label: string; tone: Tone; status: string; detail: ReactNode };

/** Live progress from the API: what is set up and what to do next. */
export function SetupChecklist() {
  const readiness = useReadiness();
  const services = useServices();
  const summary = useDashboardSummary();

  const ready = readiness.data?.status === "ready";
  const failed = readiness.data?.checks.find((c) => c.status === "fail");
  const unreachable = readiness.isError && (!(readiness.error instanceof ApiError) || readiness.error.unavailable);
  const workloads = services.data?.items.length ?? 0;
  const total = summary.data?.total ?? 0;

  const items: Item[] = [
    {
      label: "Engine API reachable and ready",
      tone: readiness.isPending ? "neutral" : ready ? "success" : "danger",
      status: readiness.isPending ? "Checking" : ready ? "Done" : unreachable ? "Unreachable" : "Not ready",
      detail: ready ? (
        "The API answers and its database is migrated."
      ) : (
        <a href={`#${unreachable ? "api-unreachable" : (failed?.reason ?? "database_unreachable")}`} className="text-accent hover:underline">
          See the fix below
        </a>
      ),
    },
    {
      label: "Workloads discovered in the cluster",
      tone: services.isPending ? "neutral" : workloads ? "success" : "warning",
      status: services.isPending ? "Checking" : services.isError ? "Unavailable" : workloads ? `${workloads} found` : "None",
      detail: workloads ? (
        <Link href="/services" className="text-accent hover:underline">
          Browse services
        </Link>
      ) : (
        <a href="#no-workloads" className="text-accent hover:underline">
          Why none are listed
        </a>
      ),
    },
    {
      label: "First experiment run",
      tone: summary.isPending ? "neutral" : total ? "success" : "info",
      status: summary.isPending ? "Checking" : total ? `${total} recorded` : "Not yet",
      detail: total ? (
        <Link href="/experiments" className="text-accent hover:underline">
          Experiment history
        </Link>
      ) : (
        <Link href="/experiments/new" className="text-accent hover:underline">
          Create an experiment
        </Link>
      ),
    },
  ];

  return (
    <ol className="divide-y divide-line" aria-label="Setup progress">
      {items.map((item, i) => (
        <li key={item.label} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-start gap-3">
            <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-surface-3 font-mono text-2xs text-muted">
              {i + 1}
            </span>
            <div className="min-w-0">
              <p className="text-sm text-fg">{item.label}</p>
              <p className="mt-0.5 text-xs text-muted">{item.detail}</p>
            </div>
          </div>
          <Badge tone={item.tone} dot>
            {item.status}
          </Badge>
        </li>
      ))}
    </ol>
  );
}
