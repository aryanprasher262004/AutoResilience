"use client";

import { openGuide } from "@/components/onboarding/guide-state";
import { Button } from "@/components/ui/button";

export function OpenGuideButton({ label = "Replay the guide" }: { label?: string }) {
  return (
    <Button variant="primary" onClick={() => openGuide()}>
      {label}
    </Button>
  );
}
