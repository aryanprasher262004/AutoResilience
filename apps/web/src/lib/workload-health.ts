import type { Tone } from "@/components/ui/badge";

import type { WorkloadHealth } from "./api/types";

/** How each backend health value is shown. Typed against the generated union. */
export const HEALTH_META: Record<WorkloadHealth, { label: string; tone: Tone; rank: number; description: string }> = {
  UNAVAILABLE: { label: "Unavailable", tone: "danger", rank: 0, description: "No ready replicas" },
  DEGRADED: { label: "Degraded", tone: "warning", rank: 1, description: "Fewer ready replicas than desired" },
  UNKNOWN: { label: "Unknown", tone: "neutral", rank: 2, description: "The cluster could not be queried" },
  NOT_FOUND: { label: "Not in cluster", tone: "neutral", rank: 3, description: "The workload no longer exists" },
  SCALED_TO_ZERO: { label: "Scaled to zero", tone: "neutral", rank: 4, description: "0 replicas desired" },
  HEALTHY: { label: "Healthy", tone: "success", rank: 5, description: "All desired replicas ready" },
};
