/**
 * Friendly names for the generated API types (schema.ts is generated from
 * packages/contracts/openapi.json by scripts/gen-api-contracts.sh; never edit it).
 */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Experiment = Schemas["ExperimentRead"];
export type ExperimentCreate = Schemas["ExperimentCreate"];
export type ExperimentState = Schemas["ExperimentState"];
export type ExperimentTarget = Schemas["ExperimentTargetSchema"];
export type FaultType = Schemas["FaultType"];
export type PodDeleteMode = Schemas["PodDeleteMode"];
export type WorkloadKind = Schemas["WorkloadKind"];
export type ValidationResult = Schemas["ValidationResultRead"];
export type Baseline = Schemas["BaselineRead"];
export type Chaos = Schemas["ChaosRead"];
export type Observation = Schemas["ObservationRead"];
export type Score = Schemas["ScoreRead"];
export type ScoreComponent = Schemas["ScoreComponentRead"];
export type AbortRequest = Schemas["AbortRequest"];

/** GET /health (the route has no response model). */
export type Health = { status: string };
