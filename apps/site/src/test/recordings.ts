import { join } from "node:path";

import { loadRecordings } from "@/lib/recordings/load";
import type { RecordedExperiment, RecordedValidation } from "@/lib/recordings/types";

/** The committed, real recordings (repository recordings/), loaded like the site does. */
export const COMMITTED_DIR = join(__dirname, "../../../../recordings");

const { recordings } = loadRecordings(COMMITTED_DIR);

function experiment(name: string): RecordedExperiment {
  const found = recordings.find((r) => r.kind === "experiment" && r.data.experiment.target.name === name);
  if (!found || found.kind !== "experiment") throw new Error(`no committed recording for ${name}`);
  return found.data;
}

export const fragile = () => experiment("fragile");
export const checkout = () => experiment("checkout");
export function rejection(): RecordedValidation {
  const found = recordings.find((r) => r.kind === "validation");
  if (!found || found.kind !== "validation") throw new Error("no committed validation recording");
  return found.data;
}

/** A deep copy to modify, e.g. to remove evidence. */
export function copy<T>(value: T): T {
  return structuredClone(value);
}
