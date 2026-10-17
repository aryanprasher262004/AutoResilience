import { useSyncExternalStore } from "react";

import type { PodDeleteMode } from "./api/types";
import { POD_DELETE_MODES } from "./experiment-options";

/**
 * Per-browser console preferences (localStorage). They only pre-fill the experiment
 * builder and remember the guide: every value is still sent to, and decided by, the
 * server's namespace-bound safety policy. Nothing here can relax a limit.
 */
export type ExperimentDefaults = {
  durationSeconds: number;
  affectedReplicas: number;
  mode: PodDeleteMode;
};

export type Preferences = {
  version: 1;
  experimentDefaults: ExperimentDefaults;
  /** When the first-use guide was finished or skipped; null shows it on the next visit. */
  guideDismissedAt: string | null;
};

export const STORAGE_KEY = "autoresilience.console.preferences";

export const BUILT_IN_DEFAULTS: ExperimentDefaults = { durationSeconds: 60, affectedReplicas: 1, mode: "GRACEFUL" };

export const DEFAULT_PREFERENCES: Preferences = {
  version: 1,
  experimentDefaults: BUILT_IN_DEFAULTS,
  guideDismissedAt: null,
};

const positiveInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v > 0;

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
    guideDismissedAt: typeof d.guideDismissedAt === "string" ? d.guideDismissedAt : null,
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
