import type { ExperimentState } from "./api/types";

/**
 * Explanatory text only. It describes what the engine does; it never decides anything.
 * Limits and verdicts always come from the API response being shown.
 */

/** What the engine is doing in each non-terminal state, and what ends it. */
export const PHASE_GUIDE: Partial<Record<ExperimentState, { doing: string; evidence: string; next: string }>> = {
  CREATED: {
    doing: "Waiting for the orchestrator to pick up the run. Nothing has touched the cluster.",
    evidence: "None yet.",
    next: "Safety validation starts on the next orchestrator tick.",
  },
  VALIDATING: {
    doing: "The server checks the experiment against the namespace's safety policy and the live workload.",
    evidence: "Static and cluster check results.",
    next: "All checks pass → baseline. Any other result → Validation failed, nothing injected.",
  },
  BASELINING: {
    doing: "Capturing the steady state from Prometheus over the configured baseline window.",
    evidence: "Availability and restarts (required), server requests and client-side outcomes (when exposed).",
    next: "A usable baseline → injection. Without one before the deadline, the run ends undetermined.",
  },
  INJECTING: {
    doing: "Re-checking safety, then creating a LitmusChaos engine that deletes exactly the selected pods.",
    evidence: "ChaosEngine identity, targeted pods, the moment their deletion is confirmed.",
    next: "Litmus running and the targeted pods gone → observation. Otherwise Injection failed and the engine is stopped.",
  },
  OBSERVING: {
    doing: "Litmus holds the fault for its duration while each step reads Litmus, Kubernetes and Prometheus once.",
    evidence: "Replacement pod times, sampled availability, server errors, client failures and outage duration.",
    next: "Litmus finishes → the recovery rule is applied.",
  },
  RECOVERING: {
    doing: "Applying the recovery rule to the recorded evidence.",
    evidence: "Replacement Ready times, consecutive stable availability samples, error ratio after recovery.",
    next: "Rule holds and Litmus passed → Completed and scored. Otherwise Undetermined, with a reason and a cause.",
  },
};

/** Plain-language background for each server check. The verdict and numbers come from the API. */
export const CHECK_HELP: Record<string, string> = {
  fault_type_supported: "Only fault types with a vetted, code-reviewed implementation can run. Today that is pod-delete.",
  namespace_not_forbidden: "System and platform namespaces (Kubernetes, monitoring, Litmus) are never a target.",
  namespace_allowed: "Some policies are bound to an allowlist of namespaces, such as the reduced-redundancy sandbox.",
  duration_within_limit: "The policy caps how long a fault may last.",
  affected_replicas_within_limit: "The policy caps how many pods one experiment may delete at once (blast radius).",
  target_workload_exists: "The Deployment or StatefulSet must exist in the cluster right now.",
  target_has_running_pods: "The workload must have running, ready pods to delete.",
  min_healthy_replicas_after_fault:
    "Enough ready pods must remain after the deletion. Scale the workload up or delete fewer pods; this is checked again just before injection.",
};

export const SUPPORTED_FAULT = {
  type: "pod-delete",
  summary:
    "Deletes the selected pods of a Deployment or StatefulSet once, then observes how the workload and its clients recover.",
  unsupported:
    "Other fault types exist in the API contract but are rejected by safety validation until a vetted implementation exists.",
};
