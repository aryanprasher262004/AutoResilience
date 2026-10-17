// Build-time only (node:fs); imported from server components of the static export.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { checkRecording } from "./check";
import type { Recording, RejectedFile } from "./types";

/** Committed recordings (repository `recordings/`), read once at build time. */
export function recordingsDir(): string {
  return process.env.RECORDINGS_DIR ?? resolve(process.cwd(), "../../recordings");
}

export function sha256(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

export function loadRecordings(dir: string = recordingsDir()): {
  recordings: Recording[];
  rejected: RejectedFile[];
} {
  let files: string[];
  try {
    files = readdirSync(dir).filter((name) => name.endsWith(".json")).sort();
  } catch {
    return { recordings: [], rejected: [] };
  }
  const recordings: Recording[] = [];
  const rejected: RejectedFile[] = [];
  for (const file of files) {
    const result = checkRecording(file, readFileSync(join(dir, file), "utf8"), sha256);
    if ("reason" in result) rejected.push(result);
    else recordings.push(result);
  }
  return { recordings, rejected };
}
