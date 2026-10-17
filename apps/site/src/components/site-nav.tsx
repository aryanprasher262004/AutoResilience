"use client";

import { cn } from "@autoresilience/ui/cn";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { GITHUB_URL, NAV } from "@/lib/site";

import { LogoMark } from "./logo";

function isActive(pathname: string, href: string): boolean {
  const path = pathname.replace(/\/+$/, "") || "/";
  return path === href || path.startsWith(`${href}/`);
}

/** Floating, translucent top bar; condenses once the page scrolls. */
export function SiteNav() {
  const pathname = usePathname();
  const [condensed, setCondensed] = useState(false);
  const [open, setOpen] = useState(false);
  const [openedAt, setOpenedAt] = useState(pathname);

  // Close the mobile menu after navigating (state reset during render, no effect needed).
  if (openedAt !== pathname) {
    setOpenedAt(pathname);
    setOpen(false);
  }

  useEffect(() => {
    const onScroll = () => setCondensed(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className="fixed inset-x-0 top-0 z-50 px-3 pt-3 sm:px-5">
      <nav
        aria-label="Main"
        className={cn(
          "mx-auto max-w-6xl rounded-xl border backdrop-blur-xl transition-[padding,background-color,border-color,box-shadow] duration-300",
          condensed || open
            ? "border-line-strong/80 bg-surface/85 py-1.5 shadow-[0_8px_30px_rgb(0_0_0/0.35)]"
            : "border-line/70 bg-surface/55 py-2.5 shadow-[0_4px_20px_rgb(0_0_0/0.2)]",
        )}
      >
        <div className="flex items-center gap-4 px-3 sm:px-4">
          <Link href="/" className="flex items-center gap-2 rounded-md py-1 font-semibold tracking-tight">
            <LogoMark className="size-6" />
            <span>AutoResilience</span>
          </Link>
          <ul className="ml-auto hidden items-center gap-1 lg:flex">
            {NAV.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "rounded-md px-3 py-2 text-sm transition-colors",
                      active ? "text-fg" : "text-muted hover:text-fg",
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="ml-auto hidden rounded-md border border-line-strong px-3 py-1.5 text-sm text-muted transition-colors hover:text-fg sm:inline-flex lg:ml-2"
          >
            GitHub<span className="sr-only"> (opens in a new tab)</span>
          </a>
          <button
            type="button"
            className="ml-auto inline-flex size-9 items-center justify-center rounded-md text-muted hover:text-fg sm:ml-0 lg:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((value) => !value)}
          >
            <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
            <svg viewBox="0 0 20 20" aria-hidden className="size-5" fill="none" stroke="currentColor" strokeWidth="1.6">
              {open ? <path d="M5 5l10 10M15 5L5 15" /> : <path d="M3 6h14M3 10h14M3 14h14" />}
            </svg>
          </button>
        </div>
        <div id="mobile-nav" hidden={!open} className="lg:hidden">
          <ul className="mt-2 border-t border-line px-2 pt-2 pb-1">
            {NAV.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "block rounded-md px-3 py-2.5 text-sm",
                      active ? "bg-surface-2 text-fg" : "text-muted hover:text-fg",
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
            <li className="sm:hidden">
              <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="block rounded-md px-3 py-2.5 text-sm text-muted">
                GitHub<span className="sr-only"> (opens in a new tab)</span>
              </a>
            </li>
          </ul>
        </div>
      </nav>
    </header>
  );
}
