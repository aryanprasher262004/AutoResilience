import type { components } from "./schema";

type Schemas = components["schemas"];

export type RecordedExperiment = Schemas["RecordedExperiment"];
export type RecordedValidation = Schemas["RecordedValidation"];
export type RecordedRun = Schemas["RecordedRun"];
export type ScoreComponent = Schemas["ScoreComponent"];
export type Provenance = Schemas["Provenance"];

/** A recording that passed every check at build time. */
export type Recording =
  | { kind: "experiment"; id: string; file: string; data: RecordedExperiment }
  | { kind: "validation"; id: string; file: string; data: RecordedValidation };

/** A committed file that failed a check: shown as an error, never replayed. */
export interface RejectedFile {
  file: string;
  reason: string;
}
