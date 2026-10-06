"use client";

import { useQuery } from "@tanstack/react-query";

import { isTerminal } from "../experiment-state";
import { api } from "./client";

/** Poll interval while an experiment is still being driven by the backend. */
const ACTIVE_POLL_MS = 3000;

export const queryKeys = {
  health: ["health"] as const,
  experiments: ["experiments"] as const,
  experiment: (id: string) => ["experiments", id] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    refetchInterval: 15_000,
    retry: false,
  });
}

export function useExperiments() {
  return useQuery({
    queryKey: queryKeys.experiments,
    queryFn: api.listExperiments,
    // Keep live states fresh; stop polling once everything is terminal.
    refetchInterval: (query) =>
      query.state.data?.some((e) => !isTerminal(e.state)) ? ACTIVE_POLL_MS : false,
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
