import type { Recording, RecordedExperiment } from "./types";

/** How a recorded workload is presented in the selector, derived from its evidence. */
export function describeWorkload(data: RecordedExperiment) {
  const run = data.experiment;
  const desired = run.baseline.availability.values.desired_replicas;
  const replicas = typeof desired === "number" ? desired : null;
  return {
    title: `${run.target.namespace}/${run.target.name}`,
    replicas,
    // Redundancy is a fact from the baseline; "resilient"/"fragile" is what the run showed.
    profile: replicas !== null && replicas > 1 ? "Redundant workload" : "Single-replica workload",
    fault: `${run.fault.type} · ${run.fault.pod_delete_mode}`,
  };
}

/** Experiment recordings first (most replicas first), then validation evidence. */
export function sortRecordings(recordings: Recording[]): Recording[] {
  const replicas = (r: Recording) =>
    r.kind === "experiment" ? (describeWorkload(r.data).replicas ?? 0) : -1;
  return [...recordings].sort((a, b) => replicas(b) - replicas(a) || a.id.localeCompare(b.id));
}
