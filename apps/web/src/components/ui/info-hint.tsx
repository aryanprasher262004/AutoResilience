"use client";

import { type ReactNode, useEffect, useId, useRef, useState } from "react";

/** A small "?" beside a complex control that explains it in place, without leaving the page. */
export function InfoHint({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <span ref={root} className="relative inline-flex align-middle">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`About ${label}`}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(event) => {
          if (event.key === "Escape" && open) {
            event.stopPropagation();
            setOpen(false);
          }
        }}
        className="inline-flex size-4 items-center justify-center rounded-full border border-line-strong font-sans text-[10px] leading-none font-medium text-muted hover:border-accent hover:text-fg"
      >
        ?
      </button>
      <span
        id={id}
        hidden={!open}
        className="absolute top-full left-0 z-40 mt-1.5 w-72 max-w-[calc(100vw-3rem)] rounded-md border border-line-strong bg-surface-3 px-3 py-2 text-left text-xs leading-relaxed font-normal tracking-normal text-muted normal-case shadow-lg [&_code]:font-mono [&_code]:text-fg"
      >
        {children}
      </span>
    </span>
  );
}
