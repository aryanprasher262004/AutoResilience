import { useSyncExternalStore } from "react";

import type { PageId } from "@/lib/help-content";

/** The running tour, shared by the tour host, the top bar, Help and Settings (one per tab). */
export type ActiveTour = { page: PageId; step: number };

let active: ActiveTour | null = null;
/** Where focus was when the tour began; it goes back there when the tour ends. */
let returnFocus: HTMLElement | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function startTour(page: PageId, step = 0) {
  if (!active && typeof document !== "undefined") returnFocus = document.activeElement as HTMLElement | null;
  active = { page, step };
  emit();
}

export function setTourStep(step: number) {
  if (!active) return;
  active = { ...active, step };
  emit();
}

export function endTour() {
  const focus = returnFocus;
  active = null;
  returnFocus = null;
  emit();
  if (focus?.isConnected) focus.focus({ preventScroll: true });
}

export function useActiveTour(): ActiveTour | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => active,
    () => null,
  );
}
