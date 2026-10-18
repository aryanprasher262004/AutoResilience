import { useSyncExternalStore } from "react";

import type { PodDeleteMode } from "./api/types";
import { POD_DELETE_MODES } from "./experiment-options";
import { PAGE_HELP, type PageId } from "./help-content";

/**
 * Per-browser console preferences (localStorage). They only pre-fill the experiment
 * builder and remember which page tours were seen: every value is still sent to, and decided by, the
 * server's namespace-bound safety policy. Nothing here can relax a limit.
 */
export type ExperimentDefaults = {
  durationSeconds: number;
  affectedReplicas: number;
  mode: PodDeleteMode;
};

/** A page tour that was finished or skipped; a page without a record shows its tour on the next visit. */
export type TourRecord = { status: "completed" | "skipped"; at: string };

export type Preferences = {
  version: 1;
  experimentDefaults: ExperimentDefaults;
  tours: Partial<Record<PageId, TourRecord>>;
};

export const STORAGE_KEY = "autoresilience.console.preferences";

export const BUILT_IN_DEFAULTS: ExperimentDefaults = { durationSeconds: 60, affectedReplicas: 1, mode: "GRACEFUL" };

export const DEFAULT_PREFERENCES: Preferences = {
  version: 1,
  experimentDefaults: BUILT_IN_DEFAULTS,
  tours: {},
};

const positiveInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v > 0;

function parseTours(value: unknown): Preferences["tours"] {
  if (typeof value !== "object" || value === null) return {};
  const tours: Preferences["tours"] = {};
  for (const [page, record] of Object.entries(value as Record<string, unknown>)) {
    if (!(page in PAGE_HELP) || typeof record !== "object" || record === null) continue;
    const r = record as Record<string, unknown>;
    if ((r.status === "completed" || r.status === "skipped") && typeof r.at === "string") {
      tours[page as PageId] = { status: r.status, at: r.at };
    }
  }
  return tours;
}

/** Anything unreadable or malformed falls back to the built-in values, field by field. */
export function parsePreferences(raw: string | null): Preferences {
  if (!raw) return DEFAULT_PREFERENCES;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return DEFAULT_PREFERENCES;
  }
  if (typeof data !== "object" || data === null) return DEFAULT_PREFERENCES;
  const d = data as Record<string, unknown>;
  const e = (typeof d.experimentDefaults === "object" && d.experimentDefaults !== null ? d.experimentDefaults : {}) as Record<
    string,
    unknown
  >;
  return {
    version: 1,
    experimentDefaults: {
      durationSeconds: positiveInt(e.durationSeconds) ? e.durationSeconds : BUILT_IN_DEFAULTS.durationSeconds,
      affectedReplicas: positiveInt(e.affectedReplicas) ? e.affectedReplicas : BUILT_IN_DEFAULTS.affectedReplicas,
      mode: (POD_DELETE_MODES as readonly unknown[]).includes(e.mode) ? (e.mode as PodDeleteMode) : BUILT_IN_DEFAULTS.mode,
    },
    tours: parseTours(d.tours),
  };
}

const listeners = new Set<() => void>();
let cache: { raw: string | null; value: Preferences } = { raw: null, value: DEFAULT_PREFERENCES };

function readRaw(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage blocked (private mode, policies): built-in values
  }
}

export function readPreferences(): Preferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  const raw = readRaw();
  if (raw !== cache.raw) cache = { raw, value: parsePreferences(raw) };
  return cache.value;
}

export function updatePreferences(change: (current: Preferences) => Preferences): void {
  const next = change(readPreferences());
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Not persisted; the session still sees the change through the cache.
    cache = { raw: cache.raw, value: next };
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => event.key === STORAGE_KEY && listener();
  window.addEventListener("storage", onStorage); // other tabs
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function recordTour(page: PageId, status: TourRecord["status"]): void {
  updatePreferences((p) => ({ ...p, tours: { ...p.tours, [page]: { status, at: new Date().toISOString() } } }));
}

/** Forget one page's tour (or all): it opens again on the next visit. */
export function resetTours(page?: PageId): void {
  updatePreferences((p) => {
    if (!page) return { ...p, tours: {} };
    const tours = { ...p.tours };
    delete tours[page];
    return { ...p, tours };
  });
}

export function usePreferences(): Preferences {
  return useSyncExternalStore(subscribe, readPreferences, () => DEFAULT_PREFERENCES);
}

/** False during server rendering and hydration, true afterwards. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}
