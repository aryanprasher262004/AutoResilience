"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BrandMark } from "@/components/icons";
import { RUNTIME_MODE, RUNTIME_MODES } from "@/lib/runtime";

import { ApiStatus } from "./api-status";
import { NavLinks } from "./nav";

/** Full sidebar on large screens, icon rail on tablets; phones use the top bar's menu. */
export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sticky top-0 hidden h-dvh w-16 shrink-0 flex-col border-r border-line bg-surface md:flex lg:w-60 print:hidden">
      <Link href="/" className="flex h-14 items-center gap-2.5 border-b border-line px-5 text-fg" aria-label="AutoResilience home">
        <BrandMark className="size-5 shrink-0 text-accent" />
        <span className="hidden text-sm font-semibold tracking-tight lg:inline">AutoResilience</span>
      </Link>
      <div className="flex-1 overflow-y-auto px-2.5 py-4 lg:px-3">
        <div className="hidden lg:block">
          <NavLinks pathname={pathname} />
        </div>
        <div className="lg:hidden">
          <NavLinks pathname={pathname} rail />
        </div>
      </div>
      <div className="flex min-h-12 items-center justify-center gap-2 border-t border-line px-4 py-3 lg:justify-between">
        <span className="lg:hidden">
          <ApiStatus compact />
        </span>
        <span className="hidden lg:inline">
          <ApiStatus />
        </span>
        <span
          className="hidden rounded border border-line-strong px-1.5 py-0.5 font-mono text-2xs text-faint lg:inline"
          title={RUNTIME_MODES[RUNTIME_MODE].summary}
        >
          {RUNTIME_MODES[RUNTIME_MODE].label}
        </span>
      </div>
    </aside>
  );
}
