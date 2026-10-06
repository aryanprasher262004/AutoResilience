"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { ChevronRightIcon } from "@/components/icons";
import { shortId } from "@/lib/format";

const LABELS: Record<string, string> = {
  experiments: "Experiments",
  new: "New",
  services: "Services",
  reports: "Reports",
  settings: "Settings",
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Breadcrumbs derived from the URL (ids are shortened, never looked up). */
export function TopBar() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  const crumbs = [
    { href: "/", label: "Overview" },
    ...segments.map((segment, i) => ({
      href: `/${segments.slice(0, i + 1).join("/")}`,
      label: LABELS[segment] ?? (UUID.test(segment) ? shortId(segment) : decodeURIComponent(segment)),
    })),
  ];
  // /services/<namespace>/<kind>/<name> is one page: show it as a single "namespace/name" crumb.
  if (segments[0] === "services" && segments.length === 4) {
    crumbs.splice(2, 3, { href: pathname, label: `${crumbs[2].label}/${crumbs[4].label}` });
  }
  return (
    <header className="sticky top-0 z-10 flex h-12 items-center border-b border-line bg-canvas/90 px-6 backdrop-blur print:hidden">
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-xs">
        {crumbs.map((crumb, i) => {
          const last = i === crumbs.length - 1;
          return (
            <Fragment key={crumb.href}>
              {i > 0 ? <ChevronRightIcon className="size-3.5 shrink-0 text-faint" /> : null}
              {last ? (
                <span aria-current="page" className="truncate font-medium text-fg">
                  {crumb.label}
                </span>
              ) : (
                <Link href={crumb.href} className="truncate text-muted hover:text-fg">
                  {crumb.label}
                </Link>
              )}
            </Fragment>
          );
        })}
      </nav>
    </header>
  );
}
