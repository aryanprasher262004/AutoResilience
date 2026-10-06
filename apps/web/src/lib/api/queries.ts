"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { isTerminal } from "../experiment-state";
import { api } from "./client";
import type { HistoryQuery, WorkloadKind } from "./types";

/** Poll interval while an experiment is still being driven by the backend. */
const ACTIVE_POLL_MS = 3000;
// Lists also pick up runs started elsewhere (another tab, the API) at this slower pace.
const IDLE_POLL_MS = 15_000;

export const queryKeys = {
  readiness: ["readiness"] as const,
  experiments: ["experiments"] as const,
  experiment: (id: string) => ["experiments", id] as const,
  history: (query: HistoryQuery) => ["experiments", "history", query] as const,
  dashboard: ["dashboard"] as const,
  services: ["services"] as const,
  service: (namespace: string, kind: WorkloadKind, name: string) => ["services", namespace, kind, name] as const,
};

/** Dependency readiness (GET /ready); re-checked sooner while not ready. */
export function useReadiness() {
  return useQuery({
    queryKey: queryKeys.readiness,
    queryFn: api.readiness,
    refetchInterval: (q) => (q.state.data?.status === "ready" ? 15_000 : 5_000),
    retry: false,
  });
}

export function useExperiment(id: string) {
  return useQuery({
    queryKey: queryKeys.experiment(id),
    queryFn: () => api.getExperiment(id),
    refetchInterval: (query) =>
      query.state.data && !isTerminal(query.state.data.state) ? ACTIVE_POLL_MS : false,
    retry: (failures, error) => !("status" in error && error.status === 404) && failures < 2,
  });
}

export function useExperimentHistory(query: HistoryQuery) {
  return useQuery({
    queryKey: queryKeys.history(query),
    queryFn: () => api.history(query),
    placeholderData: keepPreviousData, // no flash of empty table while paging/filtering
    // Drafts (CREATED) only change when a user acts, so they don't trigger fast polling.
    refetchInterval: (q) =>
      q.state.data?.items.some((e) => e.state !== "CREATED" && !isTerminal(e.state)) ? ACTIVE_POLL_MS : IDLE_POLL_MS,
  });
}

export function useDashboardSummary() {
  return useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: api.dashboard,
    refetchInterval: (q) => {
      const d = q.state.data;
      return d && d.outcomes.active > d.by_state.CREATED ? 5_000 : IDLE_POLL_MS;
    },
  });
}

/** Live workloads change outside AutoResilience too, so these refresh on the idle cadence. */
export function useServices() {
  return useQuery({ queryKey: queryKeys.services, queryFn: api.services, refetchInterval: IDLE_POLL_MS });
}

export function useService(namespace: string, kind: WorkloadKind, name: string) {
  return useQuery({
    queryKey: queryKeys.service(namespace, kind, name),
    queryFn: () => api.service(namespace, kind, name),
    refetchInterval: (q) =>
      q.state.data?.experiments.some((e) => e.state !== "CREATED" && !isTerminal(e.state))
        ? ACTIVE_POLL_MS
        : IDLE_POLL_MS,
  });
}
