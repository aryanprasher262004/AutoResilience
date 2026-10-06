import type { Tone } from "@/components/ui/badge";

import type { ExperimentState } from "./api/types";

type StateMeta = {
  label: string;
  tone: Tone;
  /** Whether the backend will still move this experiment on its own. */
  terminal: boolean;
  description: string;
};

/**
 * One presentation for every backend state. Tones carry meaning:
 * info = lifecycle in progress, fault = chaos is in flight, success/danger = outcome,
 * warning = undetermined (platform could not establish the result), neutral = idle/stopped.
 */
export const STATE_META: Record<ExperimentState, StateMeta> = {
  CREATED: { label: "Created", tone: "neutral", terminal: false, description: "Not started" },
  VALIDATING: {
    label: "Validating",
    tone: "info",
    terminal: false,
    description: "Running static and cluster safety checks",
  },
  BASELINING: {
    label: "Baselining",
    tone: "info",
    terminal: false,
    description: "Capturing the steady-state baseline from Prometheus",
  },
  INJECTING: {
    label: "Injecting",
    tone: "fault",
    terminal: false,
    description: "Starting the fault through LitmusChaos",
  },
  OBSERVING: {
    label: "Observing",
    tone: "fault",
    terminal: false,
    description: "Fault active; waiting for the Litmus run to finish",
  },
  RECOVERING: {
    label: "Recovering",
    tone: "info",
    terminal: false,
    description: "Waiting for evidence that the target recovered",
  },
  COMPLETED: {
    label: "Completed",
    tone: "success",
    terminal: true,
    description: "Target recovered; evidence and score recorded",
  },
  VALIDATION_FAILED: {
    label: "Validation failed",
    tone: "danger",
    terminal: true,
    description: "Blocked by safety checks; no fault was injected",
  },
  INJECTION_FAILED: {
    label: "Injection failed",
    tone: "danger",
    terminal: true,
    description: "The fault could not be started or confirmed",
  },
  ABORTED: { label: "Aborted", tone: "neutral", terminal: true, description: "Stopped by request" },
  UNKNOWN: {
    label: "Undetermined",
    tone: "warning",
    terminal: true,
    description: "Outcome could not be established reliably; see reason",
  },
};

/** Happy-path order, for steppers/timelines. */
export const LIFECYCLE: ExperimentState[] = [
  "CREATED",
  "VALIDATING",
  "BASELINING",
  "INJECTING",
  "OBSERVING",
  "RECOVERING",
  "COMPLETED",
];

export function isTerminal(state: ExperimentState): boolean {
  return STATE_META[state].terminal;
}
