"use client";

import { openGuide } from "@/components/onboarding/guide-state";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { updatePreferences, useHydrated, usePreferences } from "@/lib/preferences";

export function GuideControls() {
  const hydrated = useHydrated();
  const dismissed = usePreferences().guideDismissedAt;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted">
        {!hydrated
          ? "Checking…"
          : dismissed
            ? `Finished or skipped ${formatDateTime(dismissed)}.`
            : "Not finished yet: it opens on your next visit."}
      </p>
      <div className="flex gap-2">
        <Button
          variant="ghost"
          disabled={!dismissed}
          onClick={() => updatePreferences((p) => ({ ...p, guideDismissedAt: null }))}
        >
          Show on next visit
        </Button>
        <Button onClick={() => openGuide()}>Open the guide</Button>
      </div>
    </div>
  );
}
