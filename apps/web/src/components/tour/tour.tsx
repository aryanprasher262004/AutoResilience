"use client";

import { usePathname } from "next/navigation";
import { type CSSProperties, useEffect, useId, useRef, useState } from "react";

import { CloseIcon } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { RichText } from "@/components/ui/rich-text";
import { cn } from "@/lib/cn";
import { PAGE_HELP, type PageId, type TourStep, type TourTarget, pageFor } from "@/lib/help-content";
import { recordTour, useHydrated, usePreferences } from "@/lib/preferences";

import { endTour, setTourStep, startTour, useActiveTour } from "./tour-state";

/** Delay before a first-visit tour opens, so the page's data and controls have rendered. */
const AUTO_START_MS = 700;
/** How long a step looks for its control before saying it is not on screen. */
const SEARCH_MS = 600;
const MEASURE_MS = 200;
const PAD = 6;
const GAP = 12;
const MARGIN = 16;
const SHEET_BELOW = 640; // px: phones get a bottom sheet instead of a floating card

type Rect = { top: number; left: number; width: number; height: number };
type Size = { width: number; height: number };
export type Placement = { kind: "sheet" } | { kind: "center" } | { kind: "float"; top: number; left: number };

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, hi));

/** Where the step card goes: below, above, right or left of the control, else a corner. */
export function placeCard(rect: Rect | null, card: Size, viewport: Size): Placement {
  if (viewport.width < SHEET_BELOW) return { kind: "sheet" };
  if (!rect) return { kind: "center" };
  const { width: w, height: h } = card;
  const { width: vw, height: vh } = viewport;
  const left = clamp(rect.left, MARGIN, vw - w - MARGIN);
  const bottom = rect.top + rect.height;
  if (bottom + GAP + h <= vh - MARGIN) return { kind: "float", top: bottom + GAP, left };
  if (rect.top - GAP - h >= MARGIN) return { kind: "float", top: rect.top - GAP - h, left };
  const top = clamp(rect.top, MARGIN, vh - h - MARGIN);
  if (rect.left + rect.width + GAP + w <= vw - MARGIN) return { kind: "float", top, left: rect.left + rect.width + GAP };
  if (rect.left - GAP - w >= MARGIN) return { kind: "float", top, left: rect.left - GAP - w };
  return { kind: "float", top: vh - h - MARGIN, left: vw - w - MARGIN };
}

/** The first rendered element marked with the target (responsive layouts hide the others). */
function findVisible(target: TourTarget): HTMLElement | null {
  for (const el of document.querySelectorAll<HTMLElement>(`[data-tour="${target}"]`)) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return el;
  }
  return null;
}

const sameRect = (a: Rect | null, b: Rect | null) =>
  a === b || (!!a && !!b && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height);

function reducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Mounted once in the shell. Knows the page from the URL, opens that page's tour on the
 * first visit and remembers when it was finished or skipped (this browser only).
 */
export function TourHost() {
  const pathname = usePathname();
  const page = pageFor(pathname);
  const steps = PAGE_HELP[page].tour;
  const hydrated = useHydrated();
  const record = usePreferences().tours[page];
  const active = useActiveTour();

  // A tour belongs to its page: navigating away ends it unrecorded, so it is offered again.
  useEffect(() => {
    if (active && active.page !== page) endTour();
  }, [active, page]);

  useEffect(() => {
    if (!hydrated || !steps || record || active) return;
    const timer = setTimeout(() => startTour(page), AUTO_START_MS);
    return () => clearTimeout(timer);
  }, [hydrated, steps, record, active, page]);

  if (!active || active.page !== page || !steps) return null;
  const step = Math.min(active.step, steps.length - 1);
  return <TourCard key={`${page}:${step}`} page={page} steps={steps} step={step} />;
}

function TourCard({ page, steps, step }: { page: PageId; steps: TourStep[]; step: number }) {
  const current = steps[step];
  const last = step === steps.length - 1;
  const titleId = useId();
  const bodyId = useId();
  const card = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [element, setElement] = useState<HTMLElement | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);
  const [searching, setSearching] = useState(!!current.target);
  const [size, setSize] = useState<Size>({ width: 352, height: 220 });
  const [viewport, setViewport] = useState<Size>({ width: 1024, height: 768 });

  const next = () => (last ? finish() : setTourStep(step + 1));
  const finish = () => {
    recordTour(page, "completed");
    endTour();
  };
  const skip = () => {
    recordTour(page, "skipped");
    endTour();
  };

  // Find the control, keep the spotlight on it while the page moves, and notice when it
  // appears late (data loading) or goes away (filtered, collapsed).
  useEffect(() => {
    const started = Date.now();
    let scrolled = false;
    const measure = () => {
      const el = current.target ? findVisible(current.target) : null;
      if (el && !scrolled) {
        scrolled = true;
        el.scrollIntoView?.({ block: "center", inline: "nearest", behavior: reducedMotion() ? "auto" : "smooth" });
      }
      const r = el?.getBoundingClientRect();
      const nextRect = r ? { top: r.top, left: r.left, width: r.width, height: r.height } : null;
      setElement(el);
      setRect((prev) => (sameRect(prev, nextRect) ? prev : nextRect));
      setSearching(!el && !!current.target && Date.now() - started < SEARCH_MS);
      setViewport((prev) =>
        prev.width === window.innerWidth && prev.height === window.innerHeight
          ? prev
          : { width: window.innerWidth, height: window.innerHeight },
      );
      const c = card.current;
      if (c) setSize((prev) => (prev.width === c.offsetWidth && prev.height === c.offsetHeight ? prev : { width: c.offsetWidth, height: c.offsetHeight }));
    };
    const frame = requestAnimationFrame(measure);
    const timer = setInterval(measure, MEASURE_MS);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      cancelAnimationFrame(frame);
      clearInterval(timer);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [current.target]);

  // Using the highlighted control (a safe, view-only one) moves the tour on.
  useEffect(() => {
    if (!element || !current.advance) return;
    const type = current.advance === "toggle" ? "toggle" : "click";
    const onUse = () => {
      if (type === "toggle" && !(element as HTMLDetailsElement).open) return;
      setTimeout(() => (last ? finish() : setTourStep(step + 1)), 0);
    };
    element.addEventListener(type, onUse);
    return () => element.removeEventListener(type, onUse);
    // finish only records and ends; it needs no fresh closure.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [element, current.advance, last, step]);

  // Escape skips from anywhere (focus may be on the highlighted control).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      recordTour(page, "skipped");
      endTour();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [page]);

  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, []);

  const missing = !!current.target && !element && !searching;
  const placement = placeCard(rect, size, viewport);
  const hole = rect
    ? {
        top: Math.max(0, rect.top - PAD),
        left: Math.max(0, rect.left - PAD),
        right: Math.min(viewport.width, rect.left + rect.width + PAD),
        bottom: Math.min(viewport.height, rect.top + rect.height + PAD),
      }
    : null;
  const interactive = !!current.advance && !!element;
  const dim = "fixed z-[55] bg-canvas/70 motion-safe:transition-all";
  const cardStyle: CSSProperties | undefined =
    placement.kind === "float" ? { top: placement.top, left: placement.left } : undefined;

  return (
    <div className="print:hidden">
      {hole ? (
        <>
          <div aria-hidden className={dim} style={{ top: 0, left: 0, right: 0, height: hole.top }} />
          <div aria-hidden className={dim} style={{ top: hole.bottom, left: 0, right: 0, bottom: 0 }} />
          <div aria-hidden className={dim} style={{ top: hole.top, left: 0, width: hole.left, height: hole.bottom - hole.top }} />
          <div aria-hidden className={dim} style={{ top: hole.top, left: hole.right, right: 0, height: hole.bottom - hole.top }} />
          <div
            aria-hidden
            data-testid="tour-spotlight"
            className={cn(
              "fixed z-[55] rounded-lg ring-2 ring-accent motion-safe:transition-all",
              interactive ? "pointer-events-none" : "pointer-events-auto",
            )}
            style={{ top: hole.top, left: hole.left, width: hole.right - hole.left, height: hole.bottom - hole.top }}
          />
        </>
      ) : (
        <div aria-hidden className={cn(dim, "inset-0")} />
      )}

      <div
        ref={card}
        role="dialog"
        aria-modal="false"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight") {
            event.preventDefault();
            next();
          } else if (event.key === "ArrowLeft" && step > 0) {
            event.preventDefault();
            setTourStep(step - 1);
          }
        }}
        style={cardStyle}
        className={cn(
          "fixed z-[56] flex flex-col border border-line-strong bg-surface text-sm shadow-[0_24px_80px_rgb(0_0_0/0.55)] motion-safe:animate-[rise-in_200ms_ease-out]",
          placement.kind === "sheet"
            ? "inset-x-0 bottom-0 max-h-[50dvh] rounded-t-2xl"
            : "w-[22rem] max-w-[calc(100vw-2rem)] rounded-xl",
          placement.kind === "center" && "top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2",
        )}
      >
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2">
          <p className="text-2xs text-muted">
            Tour · {PAGE_HELP[page].title} · {step + 1} of {steps.length}
          </p>
          <button
            type="button"
            onClick={skip}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-2xs text-muted hover:bg-surface-2 hover:text-fg"
          >
            Skip tour
            <CloseIcon className="size-3.5" />
          </button>
        </header>
        <div className="overflow-y-auto px-4 pt-3 pb-4">
          <h2 ref={heading} id={titleId} tabIndex={-1} className="text-base font-semibold tracking-tight text-fg outline-none">
            {current.title}
          </h2>
          <p id={bodyId} className="mt-1.5 text-xs leading-relaxed text-muted">
            <RichText text={current.body} />
          </p>
          {interactive && current.tryIt ? <p className="mt-2 text-xs font-medium text-accent">{current.tryIt}</p> : null}
          {missing ? (
            <p role="status" className="mt-3 rounded-md border border-line bg-surface-2 px-3 py-2 text-xs text-muted">
              <span className="font-medium text-fg">Not on screen right now.</span>{" "}
              {current.missing ?? "This control is not shown at the moment."}
            </p>
          ) : null}
        </div>
        <footer className="flex items-center justify-between gap-2 border-t border-line px-4 py-2.5">
          <Button size="sm" variant="ghost" onClick={() => setTourStep(step - 1)} disabled={step === 0}>
            Back
          </Button>
          <ol className="flex gap-1" aria-label="Tour steps">
            {steps.map((s, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => setTourStep(i)}
                  aria-current={i === step ? "step" : undefined}
                  aria-label={`Step ${i + 1}: ${s.title}`}
                  className={cn("block size-2 rounded-full", i === step ? "bg-accent" : i < step ? "bg-accent/40" : "bg-surface-3 hover:bg-line-strong")}
                />
              </li>
            ))}
          </ol>
          <Button size="sm" variant="primary" onClick={next}>
            {last ? "Finish" : "Next"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
