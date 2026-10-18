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
  environment: ["environment"] as const,
  experiments: ["experiments"] as const,
  experiment: (id: string) => ["experiments", id] as const,
  history: (query: HistoryQuery) => ["experiments", "history", query] as const,
  dashboard: ["dashboard"] as const,
  services: ["services"] as const,
  service: (namespace: string, kind: WorkloadKind, name: string) => ["services", namespace, kind, name] as const,
  clusters: ["clusters"] as const,
  namespaces: (context: string | null) => ["clusters", context, "namespaces"] as const,
  topology: (context: string | null, namespaces: string[]) => ["topology", context, namespaces] as const,
  applications: ["applications"] as const,
  application: (id: string) => ["applications", id] as const,
  applicationTopology: (id: string) => ["applications", id, "topology"] as const,
};

/** Topology is a snapshot of live state; it is re-read on this cadence while shown. */
export const TOPOLOGY_POLL_MS = IDLE_POLL_MS;

/** Dependency readiness (GET /ready); re-checked sooner while not ready. */
export function useReadiness() {
  return useQuery({
    queryKey: queryKeys.readiness,
    queryFn: api.readiness,
    refetchInterval: (q) => (q.state.data?.status === "ready" ? 15_000 : 5_000),
    retry: false,
  });
}

/** The engine's view of its dependencies (GET /environment); probes the cluster, so polled slowly. */
export function useEnvironment() {
  return useQuery({
    queryKey: queryKeys.environment,
    queryFn: api.environment,
    refetchInterval: (q) => (q.state.data?.checks.every((c) => c.status === "pass") ? 30_000 : 10_000),
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

export function useClusters() {
  return useQuery({ queryKey: queryKeys.clusters, queryFn: api.clusters });
}

export function useNamespaces(context: string | null, enabled = true) {
  return useQuery({ queryKey: queryKeys.namespaces(context), queryFn: () => api.namespaces(context), enabled });
}

/** Onboarding preview: the topology of namespaces not saved as an application yet. */
export function useTopologyPreview(context: string | null, namespaces: string[], enabled = true) {
  return useQuery({
    queryKey: queryKeys.topology(context, namespaces),
    queryFn: () => api.topology(context, namespaces),
    enabled: enabled && namespaces.length > 0,
  });
}

export function useApplications() {
  return useQuery({ queryKey: queryKeys.applications, queryFn: api.applications });
}

export function useApplication(id: string) {
  return useQuery({
    queryKey: queryKeys.application(id),
    queryFn: () => api.application(id),
    retry: (failures, error) => !("status" in error && error.status === 404) && failures < 2,
  });
}

/** Failed refreshes keep the last snapshot (shown as stale with its observed_at). */
export function useApplicationTopology(id: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.applicationTopology(id),
    queryFn: () => api.applicationTopology(id),
    refetchInterval: TOPOLOGY_POLL_MS,
    enabled,
    retry: false,
  });
}
