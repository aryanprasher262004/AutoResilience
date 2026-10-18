"use client";

import { type ReactNode, useCallback, useEffect, useId, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/cn";

type Box = { top: number; left: number; width: number; height: number };
export type Placement = { top: number; left: number; side: "top" | "bottom"; maxWidth: number };

/** Space kept between the tooltip and the viewport edge, and between it and its control. */
export const VIEWPORT_MARGIN = 8;
const GAP = 6;
const MAX_WIDTH = 256;

/**
 * Where a tooltip of `size` goes for a control at `anchor` (viewport coordinates):
 * above it if it fits, otherwise below (whichever has more room), shifted sideways so
 * it never leaves the viewport, and never wider than the viewport allows.
 */
export function placeTooltip(
  anchor: Box,
  size: { width: number; height: number },
  viewport: { width: number; height: number },
): Placement {
  const maxWidth = Math.max(0, Math.min(MAX_WIDTH, viewport.width - 2 * VIEWPORT_MARGIN));
  const width = Math.min(size.width, maxWidth);
  const above = anchor.top - GAP - size.height;
  const below = anchor.top + anchor.height + GAP;
  const fitsAbove = above >= VIEWPORT_MARGIN;
  const fitsBelow = below + size.height <= viewport.height - VIEWPORT_MARGIN;
  const roomAbove = anchor.top;
  const roomBelow = viewport.height - (anchor.top + anchor.height);
  const side = fitsAbove || (!fitsBelow && roomAbove >= roomBelow) ? "top" : "bottom";
  const top = side === "top" ? Math.max(VIEWPORT_MARGIN, above) : below;
  const left = Math.min(
    Math.max(VIEWPORT_MARGIN, anchor.left),
    Math.max(VIEWPORT_MARGIN, viewport.width - VIEWPORT_MARGIN - width),
  );
  return { top, left, side, maxWidth };
}

const subscribe = () => () => {};

/**
 * A description shown on hover and keyboard focus, dismissible with Escape. The control
 * references it with `aria-describedby` (passed to `children`), so it is announced too.
 *
 * Rendered in a portal with fixed, collision-aware placement, so scroll areas, the
 * graph canvas or a narrow inspector never clip it.
 */
export function Tooltip({ content, children }: { content: ReactNode; children: (describedBy: string) => ReactNode }) {
  const id = useId();
  const anchor = useRef<HTMLSpanElement>(null);
  const tip = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  // The portal target exists only in the browser.
  const mounted = useSyncExternalStore(subscribe, () => true, () => false);

  const measure = useCallback(() => {
    if (!anchor.current || !tip.current) return;
    const a = anchor.current.getBoundingClientRect();
    const t = tip.current.getBoundingClientRect();
    setPlacement(
      placeTooltip(
        { top: a.top, left: a.left, width: a.width, height: a.height },
        { width: t.width, height: t.height },
        { width: window.innerWidth, height: window.innerHeight },
      ),
    );
  }, []);

  const hide = useCallback(() => {
    setShown(false);
    setPlacement(null);
  }, []);

  useLayoutEffect(() => {
    if (!shown) return;
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [shown, measure]);

  // Escape also dismisses a tooltip shown by hovering (focus is elsewhere then).
  useEffect(() => {
    if (!shown) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && hide();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shown, hide]);

  const tooltip = (
    <span
      ref={tip}
      role="tooltip"
      id={id}
      data-side={placement?.side}
      hidden={!shown}
      style={
        placement
          ? { top: placement.top, left: placement.left, maxWidth: placement.maxWidth }
          : { top: 0, left: 0, maxWidth: `min(${MAX_WIDTH}px, calc(100vw - ${2 * VIEWPORT_MARGIN}px))` }
      }
      className={cn(
        "pointer-events-none fixed z-50 w-max rounded-md border border-line-strong bg-surface-3 px-2 py-1.5 text-left text-2xs leading-relaxed font-normal break-words whitespace-normal text-fg shadow-lg",
        // Measured before it is placed: keep it invisible for that one frame.
        shown && !placement && "invisible",
      )}
    >
      {content}
    </span>
  );

  return (
    <span
      ref={anchor}
      className="relative inline-flex"
      onMouseEnter={() => setShown(true)}
      onMouseLeave={hide}
      onFocus={() => setShown(true)}
      onBlur={hide}
      onKeyDown={(event) => {
        if (event.key === "Escape" && shown) {
          event.stopPropagation();
          hide();
        }
      }}
    >
      {children(id)}
      {mounted ? createPortal(tooltip, document.body) : null}
    </span>
  );
}
