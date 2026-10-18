/**
 * Import (P7) responses for component tests. `preview`/`blocked` are real
 * POST /imports/preview outputs (the API's tests/import_fixtures.py COMPOSE and
 * examples/resiliencemart/unsafe-compose.yaml), so they match the contract exactly.
 */
import type { ImportCapabilities, ImportPreview, ImportRead, ImportStatus } from "@/lib/api/types";

import data from "./import-fixtures.json";

export const IMPORT_ID = "5b1d3c2e-8a4f-4c6e-9d7a-1f2e3d4c5b6a";
export const APP_ID = "9c8b7a6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d";

export const preview = (): ImportPreview => structuredClone(data.preview) as ImportPreview;
export const blocked = (): ImportPreview => structuredClone(data.blocked) as ImportPreview;

export function importRead(status: ImportStatus = "PLANNED", overrides: Partial<ImportRead> = {}): ImportRead {
  const p = preview();
  return {
    id: IMPORT_ID,
    name: p.name,
    source: p.source,
    filename: p.filename,
    status,
    namespace: p.plan!.namespace,
    spec: p.spec!,
    findings: p.findings,
    plan: p.plan!,
    deployment: {
      attempts: status === "PLANNED" ? 0 : 1,
      started_at: status === "PLANNED" ? null : "2026-10-19T10:00:00Z",
      checked_at: null,
      finished_at: null,
      failing_since: null,
      error: null,
      recovery: null,
      workloads: [],
      applied: [],
      removal: null,
    },
    application_id: status === "READY" ? APP_ID : null,
    created_at: "2026-10-19T09:59:00Z",
    updated_at: "2026-10-19T10:00:00Z",
    ...overrides,
  };
}

export const capabilities = (configured = true): ImportCapabilities => ({
  provisioner: {
    configured,
    context: null,
    detail: configured
      ? "Dedicated provisioner identity verified on the execution cluster."
      : "No provisioner identity configured: imports can be reviewed and saved, not deployed. Development: scripts/dev-provisioner.sh; local stack: ar install.",
  },
  execution_context: "kind-autoresilience",
  max_bytes: 262144,
  max_documents: 50,
  max_workloads: 20,
  max_replicas: 5,
  namespace_prefix: "ar-imp-",
  compose_keys: ["image"],
  manifest_kinds: ["apps/v1 Deployment"],
});
