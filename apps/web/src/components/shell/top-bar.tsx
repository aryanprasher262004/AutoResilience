"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { BrandMark, ChevronRightIcon, CloseIcon, CompassIcon, HelpIcon, MenuIcon } from "@/components/icons";
import { openGuide } from "@/components/onboarding/guide-state";
import { shortId } from "@/lib/format";

import { ApiStatus } from "./api-status";
import { NavLinks, isKnownRoute } from "./nav";

const LABELS: Record<string, string> = {
  experiments: "Experiments",
  new: "New",
  applications: "Applications",
  services: "Services",
  reports: "Reports",
  settings: "Settings",
  help: "Help",
  "how-it-works": "How it works",
  support: "Support",
  about: "About",
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Breadcrumbs derived from the URL (ids are shortened, never looked up), plus actions. */
export function TopBar() {
  const pathname = usePathname();
  const known = isKnownRoute(pathname);
  const segments = known ? pathname.split("/").filter(Boolean) : [];
  const crumbs = [
    { href: "/", label: "Overview" },
    ...segments.map((segment, i) => ({
      href: `/${segments.slice(0, i + 1).join("/")}`,
      label: LABELS[segment] ?? (UUID.test(segment) ? shortId(segment) : decodeURIComponent(segment)),
    })),
  ];
  if (!known) crumbs.push({ href: pathname, label: "Not found" });
  // /services/<namespace>/<kind>/<name> is one page: show it as a single "namespace/name" crumb.
  if (segments[0] === "services" && segments.length === 4) {
    crumbs.splice(2, 3, { href: pathname, label: `${crumbs[2].label}/${crumbs[4].label}` });
  }
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur-md sm:px-6 print:hidden">
      <MobileMenu pathname={pathname} />
      <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-1 text-xs">
        {crumbs.map((crumb, i) => {
          const last = i === crumbs.length - 1;
          // Phones show only the current page; the menu and Back cover the rest.
          return (
            <Fragment key={crumb.href}>
              {i > 0 ? <ChevronRightIcon className="hidden size-3.5 shrink-0 text-faint sm:block" /> : null}
              {last ? (
                <span aria-current="page" className="truncate font-medium text-fg">
                  {crumb.label}
                </span>
              ) : (
                <Link href={crumb.href} className="hidden truncate text-muted hover:text-fg sm:inline">
                  {crumb.label}
                </Link>
              )}
            </Fragment>
          );
        })}
      </nav>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={() => openGuide()}
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-muted hover:bg-surface-2 hover:text-fg"
        >
          <CompassIcon className="size-4" />
          <span className="sr-only sm:not-sr-only">Guide</span>
        </button>
        <Link
          href="/help"
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-muted hover:bg-surface-2 hover:text-fg"
        >
          <HelpIcon className="size-4" />
          <span className="sr-only sm:not-sr-only">Help</span>
        </Link>
      </div>
    </header>
  );
}

/** Phones only: the sidebar's navigation in a drawer. */
function MobileMenu({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false);
  const [openedAt, setOpenedAt] = useState(pathname);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  // Navigating closes the drawer (state reset during render, no effect needed).
  if (openedAt !== pathname) {
    setOpenedAt(pathname);
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>("a, button")?.focus();
    const toggle = button.current;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      toggle?.focus();
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls="mobile-navigation"
        onClick={() => setOpen(true)}
        className="-ml-1.5 inline-flex size-9 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg"
      >
        <MenuIcon className="size-5" />
        <span className="sr-only">Open navigation</span>
      </button>
      {open
        ? createPortal(
            // Portalled: the sticky header's backdrop-filter would otherwise contain `fixed`.
            <div className="fixed inset-0 z-50 md:hidden">
              <div aria-hidden className="absolute inset-0 bg-canvas/75 backdrop-blur-sm" onClick={() => setOpen(false)} />
              <div
                ref={panel}
                id="mobile-navigation"
                role="dialog"
                aria-modal="true"
                aria-label="Navigation"
                className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-line bg-surface shadow-[0_0_60px_rgb(0_0_0/0.5)] motion-safe:animate-[fade-in_150ms_ease-out]"
              >
                <div className="flex h-14 items-center justify-between border-b border-line px-4">
                  <span className="flex items-center gap-2 text-sm font-semibold">
                    <BrandMark className="size-5 text-accent" />
                    AutoResilience
                  </span>
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="inline-flex size-9 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg"
                  >
                    <CloseIcon className="size-5" />
                    <span className="sr-only">Close navigation</span>
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  <NavLinks pathname={pathname} />
                </div>
                <div className="border-t border-line px-4 py-3">
                  <ApiStatus />
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
