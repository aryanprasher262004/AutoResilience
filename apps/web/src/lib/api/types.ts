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
export type ExperimentSummary = Schemas["ExperimentSummary"];
export type ExperimentPage = Schemas["ExperimentPage"];
export type DashboardSummary = Schemas["DashboardSummary"];
export type ScorePoint = Schemas["ScorePoint"];
export type ServiceSummary = Schemas["ServiceSummary"];
export type ServiceList = Schemas["ServiceList"];
export type ServiceDetail = Schemas["ServiceDetail"];
export type WorkloadHealth = ServiceDetail["health"];
export type Readiness = Schemas["Readiness"];
export type ReadinessReason = NonNullable<Readiness["checks"][number]["reason"]>;

/** Query parameters of GET /experiments/history (mirrors the OpenAPI operation). */
export type HistoryQuery = {
  q?: string;
  state?: ExperimentState[];
  fault_type?: FaultType[];
  namespace?: string[];
  sort?: "created_at" | "updated_at" | "name" | "score";
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
};

/** GET /health (the route has no response model). */
export type Health = { status: string };
