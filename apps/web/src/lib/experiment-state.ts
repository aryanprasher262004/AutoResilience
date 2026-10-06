import type { Tone } from "@/components/ui/badge";

import type { Experiment, ExperimentState, ExperimentSummary } from "./api/types";

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

/**
 * Presentation for a concrete experiment. A manually validated experiment waits in
 * BASELINING without a baseline until someone runs it; nothing is baselining it, so
 * say so instead of showing an in-progress state.
 */
export function presentState(e: Experiment | ExperimentSummary): StateMeta & { state: ExperimentState } {
  const summary = "has_baseline" in e;
  const auto = summary ? e.auto : (e.orchestration as { mode?: string } | null)?.mode === "auto";
  const hasBaseline = summary ? e.has_baseline : Boolean(e.baseline);
  if (e.state === "BASELINING" && !auto && !hasBaseline) {
    return {
      state: e.state,
      label: "Validated · not started",
      tone: "neutral",
      terminal: false,
      description: "Passed safety validation; waiting to be run",
    };
  }
  return { state: e.state, ...STATE_META[e.state] };
}
