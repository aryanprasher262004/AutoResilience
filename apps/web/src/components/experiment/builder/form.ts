import type { ExperimentCreate, FaultType, PodDeleteMode, WorkloadKind } from "@/lib/api/types";

/** Raw form state (strings for number inputs so partial edits are possible). */
export type FormValues = {
  name: string;
  description: string;
  namespace: string;
  workload: string;
  kind: WorkloadKind;
  faultType: FaultType;
  mode: PodDeleteMode;
  durationSeconds: string;
  affectedReplicas: string;
};

export type FieldErrors = Partial<Record<keyof FormValues, string>>;

export const INITIAL_VALUES: FormValues = {
  name: "",
  description: "",
  namespace: "",
  workload: "",
  kind: "Deployment",
  faultType: "pod-delete",
  mode: "GRACEFUL",
  durationSeconds: "60",
  affectedReplicas: "1",
};

const positiveInt = (value: string) => /^\d+$/.test(value.trim()) && Number(value) > 0;

/**
 * Only obvious input errors. Name formats, limits and every safety rule are decided
 * by the server (422 for malformed input, validation checks for safety).
 */
export function checkObvious(values: FormValues): FieldErrors {
  const errors: FieldErrors = {};
  if (!values.name.trim()) errors.name = "Required";
  if (!values.namespace.trim()) errors.namespace = "Required";
  if (!values.workload.trim()) errors.workload = "Required";
  if (!positiveInt(values.durationSeconds)) errors.durationSeconds = "Whole number of seconds, > 0";
  if (!positiveInt(values.affectedReplicas)) errors.affectedReplicas = "Whole number, > 0";
  return errors;
}

export function toPayload(values: FormValues): ExperimentCreate {
  return {
    name: values.name.trim(),
    description: values.description.trim() || null,
    target: { namespace: values.namespace.trim(), name: values.workload.trim(), kind: values.kind },
    fault_type: values.faultType,
    pod_delete_mode: values.mode,
    duration_seconds: Number(values.durationSeconds),
    affected_replicas: Number(values.affectedReplicas),
  };
}

/** FastAPI 422 body paths -> form fields. */
const SERVER_FIELDS: Record<string, keyof FormValues> = {
  name: "name",
  description: "description",
  "target.namespace": "namespace",
  "target.name": "workload",
  "target.kind": "kind",
  fault_type: "faultType",
  pod_delete_mode: "mode",
  duration_seconds: "durationSeconds",
  affected_replicas: "affectedReplicas",
};

export function serverFieldErrors(byPath: Record<string, string>): {
  fields: FieldErrors;
  other: string[];
} {
  const fields: FieldErrors = {};
  const other: string[] = [];
  for (const [path, message] of Object.entries(byPath)) {
    const field = SERVER_FIELDS[path];
    if (field) fields[field] ??= message;
    else other.push(`${path || "request"}: ${message}`);
  }
  return { fields, other };
}
