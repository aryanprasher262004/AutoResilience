"use client";

import { type KeyboardEvent, type ReactNode, useId, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export type TabItem = { id: string; label: ReactNode; content: ReactNode };

/** Accessible tabs (WAI-ARIA pattern: arrow keys move between tabs). */
export function Tabs({ items, defaultTab }: { items: TabItem[]; defaultTab?: string }) {
  const [active, setActive] = useState(defaultTab ?? items[0]?.id);
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const base = useId();

  function onKeyDown(event: KeyboardEvent, index: number) {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    const next = (index + delta + items.length) % items.length;
    setActive(items[next].id);
    refs.current[next]?.focus();
  }

  return (
    <div>
      <div role="tablist" className="flex gap-1 border-b border-line">
        {items.map((item, index) => {
          const selected = item.id === active;
          return (
            <button
              key={item.id}
              ref={(el) => {
                refs.current[index] = el;
              }}
              role="tab"
              id={`${base}-tab-${item.id}`}
              aria-selected={selected}
              aria-controls={`${base}-panel-${item.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(item.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 text-xs font-medium transition-colors",
                selected
                  ? "border-accent text-fg"
                  : "border-transparent text-muted hover:text-fg",
              )}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items.map((item) =>
        item.id === active ? (
          <div
            key={item.id}
            role="tabpanel"
            id={`${base}-panel-${item.id}`}
            aria-labelledby={`${base}-tab-${item.id}`}
            className="pt-4"
          >
            {item.content}
          </div>
        ) : null,
      )}
    </div>
  );
}
