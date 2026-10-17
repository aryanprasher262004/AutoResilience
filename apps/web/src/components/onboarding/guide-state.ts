import { useSyncExternalStore } from "react";

/** Whether the guide is open, shared by the shell, Help and Settings (one per tab). */
let open = false;
let startStep = 0;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function openGuide(step = 0) {
  open = true;
  startStep = step;
  emit();
}

export function closeGuide() {
  open = false;
  emit();
}

export function guideStartStep(): number {
  return startStep;
}

export function useGuideOpen(): boolean {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => open,
    () => false,
  );
}
