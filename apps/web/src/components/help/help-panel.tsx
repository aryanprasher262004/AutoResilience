"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef } from "react";

import { CloseIcon, HelpIcon } from "@/components/icons";
import { startTour } from "@/components/tour/tour-state";
import { Button } from "@/components/ui/button";
import { RichText } from "@/components/ui/rich-text";
import { PAGE_HELP, TOUR_TARGET, pageFor } from "@/lib/help-content";
import { usePreferences } from "@/lib/preferences";
import { docsUrl } from "@/lib/runtime";

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/**
 * The top bar's Help: a side panel about the page you are on (same content as the tours
 * and the Help page), with its tour and documentation. `?` opens it from anywhere.
 */
export function HelpButton() {
  const pathname = usePathname();
  const page = pageFor(pathname);
  const help = PAGE_HELP[page];
  const seen = usePreferences().tours[page];
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  const open = () => {
    if (!dialog.current?.open) dialog.current?.showModal();
  };
  const close = () => dialog.current?.close();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "?" || event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) return;
      if (document.querySelector("dialog[open]")) return; // another dialog has the user's attention
      event.preventDefault();
      if (!dialog.current?.open) dialog.current?.showModal();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Navigating (a link in the panel, Back) closes it.
  useEffect(() => {
    dialog.current?.close();
  }, [pathname]);

  return (
    <>
      <button
        type="button"
        onClick={open}
        data-tour={TOUR_TARGET.topBarHelp}
        aria-keyshortcuts="?"
        className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-muted hover:bg-surface-2 hover:text-fg"
      >
        <HelpIcon className="size-4" />
        <span className="sr-only sm:not-sr-only">Help</span>
      </button>
      <dialog
        ref={dialog}
        aria-labelledby={titleId}
        className="fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-dvh w-[26rem] max-w-full border-l border-line-strong bg-surface p-0 text-fg backdrop:bg-black/50 motion-safe:animate-[fade-in_150ms_ease-out]"
      >
        <div className="flex h-full flex-col">
          <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <p className="text-2xs font-medium tracking-wide text-faint uppercase">Help for this page</p>
              <h2 id={titleId} className="mt-0.5 text-base font-semibold">
                {help.title}
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-muted">{help.summary}</p>
            </div>
            <button
              type="button"
              onClick={close}
              className="-mr-1.5 inline-flex size-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg"
            >
              <CloseIcon className="size-4" />
              <span className="sr-only">Close help</span>
            </button>
          </header>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {help.tour ? (
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-surface-2/60 px-3 py-2.5">
                <p className="text-xs text-muted">
                  {help.tour.length}-step tour of this page{seen ? ` (${seen.status})` : ""}. It only highlights; it never starts anything.
                </p>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => {
                    close();
                    startTour(page);
                  }}
                >
                  {seen ? "Replay the tour" : "Take the tour"}
                </Button>
              </div>
            ) : null}

            <h3 className="text-2xs font-medium tracking-wide text-faint uppercase">On this page</h3>
            <dl className="mt-2 grid gap-3">
              {help.topics.map((t) => (
                <div key={t.title}>
                  <dt className="text-sm text-fg">{t.title}</dt>
                  <dd className="mt-0.5 text-xs leading-relaxed text-muted">
                    <RichText text={t.body} />
                  </dd>
                </div>
              ))}
            </dl>

            {help.docs.length ? (
              <>
                <h3 className="mt-5 text-2xs font-medium tracking-wide text-faint uppercase">Documentation (GitHub)</h3>
                <ul className="mt-2 grid gap-1.5 text-sm">
                  {help.docs.map((d) => (
                    <li key={d.path}>
                      <a href={docsUrl(d.path)} target="_blank" rel="noreferrer" className="text-accent hover:underline">
                        {d.label} ↗<span className="sr-only"> (opens in a new tab)</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>

          <footer className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line px-5 py-3 text-xs">
            <Link href={`/help#page-${page}`} onClick={close} className="text-accent hover:underline">
              All page guides
            </Link>
            <Link href="/help#troubleshooting" onClick={close} className="text-muted hover:text-fg">
              Troubleshooting
            </Link>
            <Link href="/how-it-works" onClick={close} className="text-muted hover:text-fg">
              How it works
            </Link>
          </footer>
        </div>
      </dialog>
    </>
  );
}
