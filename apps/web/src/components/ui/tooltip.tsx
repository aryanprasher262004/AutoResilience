"use client";

import { type ReactNode, useEffect, useId, useState } from "react";

import { cn } from "@/lib/cn";

/**
 * A description shown on hover and keyboard focus, dismissible with Escape. The control
 * references it with `aria-describedby` (passed to `children`), so it is announced too.
 */
export function Tooltip({ content, children }: { content: ReactNode; children: (describedBy: string) => ReactNode }) {
  const id = useId();
  const [shown, setShown] = useState(false);

  // Escape also dismisses a tooltip shown by hovering (focus is elsewhere then).
  useEffect(() => {
    if (!shown) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setShown(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shown]);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setShown(true)}
      onMouseLeave={() => setShown(false)}
      onFocus={() => setShown(true)}
      onBlur={() => setShown(false)}
      onKeyDown={(event) => {
        if (event.key === "Escape" && shown) {
          event.stopPropagation();
          setShown(false);
        }
      }}
    >
      {children(id)}
      <span
        role="tooltip"
        id={id}
        className={cn(
          "pointer-events-none absolute bottom-full left-0 z-40 mb-1.5 w-max max-w-64 rounded-md border border-line-strong bg-surface-3 px-2 py-1.5 text-left text-2xs leading-relaxed font-normal text-fg shadow-lg",
          !shown && "hidden",
        )}
      >
        {content}
      </span>
    </span>
  );
}
