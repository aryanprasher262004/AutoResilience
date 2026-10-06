"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentType, SVGProps } from "react";

import {
  BrandMark,
  ExperimentsIcon,
  OverviewIcon,
  PlusIcon,
  ReportsIcon,
  ServicesIcon,
  SettingsIcon,
} from "@/components/icons";
import { cn } from "@/lib/cn";

import { ApiStatus } from "./api-status";

type NavItem = {
  href: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
};

const NAV: NavItem[] = [
  { href: "/", label: "Overview", icon: OverviewIcon },
  { href: "/experiments", label: "Experiments", icon: ExperimentsIcon },
  { href: "/services", label: "Services", icon: ServicesIcon },
  { href: "/reports", label: "Reports", icon: ReportsIcon },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  // "/experiments/new" belongs to the New Experiment action, not the list.
  if (pathname === "/experiments/new") return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Full sidebar on large screens; icon rail on tablet widths. */
export function Sidebar() {
  const pathname = usePathname();
  const creating = pathname === "/experiments/new";
  return (
    <aside className="sticky top-0 flex h-dvh w-14 shrink-0 flex-col border-r border-line bg-surface lg:w-56">
      <Link
        href="/"
        className="flex h-12 items-center gap-2 border-b border-line px-4 text-fg"
        aria-label="AutoResilience home"
      >
        <BrandMark className="size-5 shrink-0 text-accent" />
        <span className="hidden text-sm font-semibold tracking-tight lg:inline">
          AutoResilience
        </span>
      </Link>

      <div className="px-2 pt-3 lg:px-3">
        <Link
          href="/experiments/new"
          aria-current={creating ? "page" : undefined}
          title="New Experiment"
          className={cn(
            "flex h-8 items-center justify-center gap-1.5 rounded-md text-sm font-medium transition-colors",
            "bg-accent text-white hover:bg-accent-strong",
            creating && "ring-2 ring-accent/40 ring-offset-2 ring-offset-surface",
          )}
        >
          <PlusIcon className="size-4" />
          <span className="hidden lg:inline">New Experiment</span>
        </Link>
      </div>

      <nav aria-label="Primary" className="mt-3 flex flex-1 flex-col gap-0.5 px-2 lg:px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              title={label}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
                "justify-center lg:justify-start",
                active
                  ? "bg-surface-3 font-medium text-fg"
                  : "text-muted hover:bg-surface-2 hover:text-fg",
              )}
            >
              <Icon className={cn("size-4 shrink-0", active && "text-accent")} />
              <span className="hidden lg:inline">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="flex h-11 items-center justify-center border-t border-line px-4 lg:justify-start">
        <span className="lg:hidden">
          <ApiStatus compact />
        </span>
        <span className="hidden lg:inline">
          <ApiStatus />
        </span>
      </div>
    </aside>
  );
}
