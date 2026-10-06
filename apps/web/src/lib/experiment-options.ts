import type { FaultType, PodDeleteMode, WorkloadKind } from "./api/types";

/**
 * Runtime option lists for the generated string unions. The `Exhaustive` checks make
 * the typecheck fail if the backend adds or removes a value without updating these.
 */
type Exhaustive<Union, List extends readonly Union[]> = [Exclude<Union, List[number]>] extends [never]
  ? List
  : never;

const workloadKinds = ["Deployment", "StatefulSet"] as const;
export const WORKLOAD_KINDS: Exhaustive<WorkloadKind, typeof workloadKinds> = workloadKinds;

const faultTypes = ["pod-delete", "pod-cpu-hog", "pod-memory-hog", "pod-network-latency"] as const;
export const FAULT_TYPES: Exhaustive<FaultType, typeof faultTypes> = faultTypes;

const podDeleteModes = ["GRACEFUL", "FORCE"] as const;
export const POD_DELETE_MODES: Exhaustive<PodDeleteMode, typeof podDeleteModes> = podDeleteModes;

export const MODE_HELP: Record<PodDeleteMode, string> = {
  GRACEFUL: "Normal deletion: the pod gets its termination grace period (SIGTERM first).",
  FORCE: "Immediate deletion with a zero grace period: no graceful shutdown.",
};
