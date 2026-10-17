import { canonicalBody } from "./canonical";
import type { RecordedExperiment, RecordedValidation, Recording, RejectedFile } from "./types";

const SCHEMAS = {
  "autoresilience-recording/1": "experiment",
  "autoresilience-validation/1": "validation",
} as const;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Build-time gate for one committed file. CI already validates every file against the
 * Pydantic contract; the site re-checks what it relies on and never replays a file that
 * fails: supported schema, integrity hash, file name, and real (non-synthetic) evidence.
 */
export function checkRecording(
  file: string,
  text: string,
  sha256: (text: string) => string,
): Recording | RejectedFile {
  const reject = (reason: string): RejectedFile => ({ file, reason });
  let data: unknown;
  let body: string;
  try {
    data = JSON.parse(text);
    body = canonicalBody(text);
  } catch (error) {
    return reject(`not valid JSON (${(error as Error).message})`);
  }
  if (!isObject(data)) return reject("not a JSON object");
  const schema = data.schema;
  if (typeof schema !== "string" || !(schema in SCHEMAS)) {
    return reject(`unsupported schema ${JSON.stringify(schema)}`);
  }
  const integrity = data.integrity;
  if (!isObject(integrity) || integrity.algorithm !== "sha256" || typeof integrity.content_sha256 !== "string") {
    return reject("integrity block missing");
  }
  if (sha256(body) !== integrity.content_sha256) {
    return reject("integrity hash does not match the content");
  }
  const id = data.recording_id;
  if (typeof id !== "string" || file !== `${id}.json`) return reject("file name does not match recording_id");
  const provenance = data.provenance;
  if (!isObject(provenance) || provenance.synthetic !== false) {
    return reject("synthetic or unlabelled evidence is never published");
  }
  if (!isObject(data.experiment)) return reject("experiment block missing");

  // Shape beyond these checks is guaranteed by the Pydantic contract, enforced in CI.
  return SCHEMAS[schema as keyof typeof SCHEMAS] === "experiment"
    ? { kind: "experiment", id, file, data: data as unknown as RecordedExperiment }
    : { kind: "validation", id, file, data: data as unknown as RecordedValidation };
}
