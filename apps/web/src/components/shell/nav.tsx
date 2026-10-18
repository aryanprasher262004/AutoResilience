"use client";

import Link from "next/link";
import type { ComponentType, SVGProps } from "react";

import {
  ApplicationsIcon,
  BookIcon,
  ExperimentsIcon,
  HelpIcon,
  InfoIcon,
  OverviewIcon,
  PlusIcon,
  ReportsIcon,
  ServicesIcon,
  SettingsIcon,
  SupportIcon,
} from "@/components/icons";
import { cn } from "@/lib/cn";
import { TOUR_TARGET } from "@/lib/help-content";
import { isKnownRoute } from "@/lib/routes";

type NavItem = { href: string; label: string; icon: ComponentType<SVGProps<SVGSVGElement>> };

export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Workspace",
    items: [
      { href: "/", label: "Overview", icon: OverviewIcon },
      { href: "/experiments", label: "Experiments", icon: ExperimentsIcon },
      { href: "/applications", label: "Applications", icon: ApplicationsIcon },
      { href: "/services", label: "Services", icon: ServicesIcon },
      { href: "/reports", label: "Reports", icon: ReportsIcon },
    ],
  },
  {
    label: "Learn",
    items: [
      { href: "/how-it-works", label: "How it works", icon: BookIcon },
      { href: "/help", label: "Help", icon: HelpIcon },
    ],
  },
  {
    label: "System",
    items: [
      { href: "/settings", label: "Settings", icon: SettingsIcon },
      { href: "/support", label: "Support", icon: SupportIcon },
      { href: "/about", label: "About", icon: InfoIcon },
    ],
  },
];

export { isKnownRoute };

export function isActive(pathname: string, href: string): boolean {
  if (!isKnownRoute(pathname)) return false;
  if (href === "/") return pathname === "/";
  // "/experiments/new" belongs to the New Experiment action, not the list.
  if (pathname === "/experiments/new") return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Primary navigation. `rail` shows icons only (tablet widths); labels stay available to
 * assistive tech and as tooltips.
 */
export function NavLinks({ pathname, rail = false }: { pathname: string; rail?: boolean }) {
  const creating = pathname === "/experiments/new";
  return (
    <>
      <Link
        href="/experiments/new"
        aria-current={creating ? "page" : undefined}
        title="New Experiment"
        data-tour={TOUR_TARGET.navNewExperiment}
        className={cn(
          "flex h-9 items-center justify-center gap-1.5 rounded-md text-sm font-medium transition-colors",
          "bg-accent text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.15)] hover:bg-accent-strong",
          creating && "ring-2 ring-accent/40 ring-offset-2 ring-offset-surface",
        )}
      >
        <PlusIcon className="size-4" />
        <span className={rail ? "sr-only" : undefined}>New Experiment</span>
      </Link>
      <nav aria-label="Primary" className="mt-4 flex flex-col gap-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            {rail ? (
              <div aria-hidden className="mx-2 mb-2 border-t border-line" />
            ) : (
              <p className="mb-1.5 px-2.5 text-2xs font-medium tracking-[0.08em] text-faint uppercase">{group.label}</p>
            )}
            <ul className="flex flex-col gap-0.5">
              {group.items.map(({ href, label, icon: Icon }) => {
                const active = isActive(pathname, href);
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      title={rail ? label : undefined}
                      data-tour={href === "/applications" ? TOUR_TARGET.navApplications : undefined}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
                        rail && "justify-center",
                        active
                          ? "bg-surface-3 font-medium text-fg shadow-[inset_0_1px_0_rgb(255_255_255/0.04)]"
                          : "text-muted hover:bg-surface-2 hover:text-fg",
                      )}
                    >
                      {active && !rail ? (
                        <span aria-hidden className="absolute top-1.5 bottom-1.5 left-0 w-0.5 rounded-full bg-accent" />
                      ) : null}
                      <Icon className={cn("size-4 shrink-0", active && "text-accent")} />
                      <span className={rail ? "sr-only" : undefined}>{label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </>
  );
}
