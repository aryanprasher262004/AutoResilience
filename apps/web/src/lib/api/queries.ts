"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { isTerminal } from "../experiment-state";
import { api } from "./client";
import type { HistoryQuery } from "./types";

/** Poll interval while an experiment is still being driven by the backend. */
const ACTIVE_POLL_MS = 3000;
// Lists also pick up runs started elsewhere (another tab, the API) at this slower pace.
const IDLE_POLL_MS = 15_000;

export const queryKeys = {
  health: ["health"] as const,
  experiments: ["experiments"] as const,
  experiment: (id: string) => ["experiments", id] as const,
  history: (query: HistoryQuery) => ["experiments", "history", query] as const,
  dashboard: ["dashboard"] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    refetchInterval: 15_000,
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
