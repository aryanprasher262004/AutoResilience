"use client";

import { usePathname, useRouter } from "next/navigation";

import { startTour } from "@/components/tour/tour-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { RichText } from "@/components/ui/rich-text";
import { PAGE_HELP, type PageId, pageFor } from "@/lib/help-content";
import { resetTours } from "@/lib/preferences";
import { docsUrl } from "@/lib/runtime";

/** Opens a page's tour: here if it is this page, else by resetting it and going there. */
export function TourLink({ page, label = "Take the tour" }: { page: PageId; label?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const help = PAGE_HELP[page];
  if (!help.tour || !help.href) return null;
  return (
    <Button
      size="sm"
      onClick={() => {
        if (pageFor(pathname) === page) startTour(page);
        else {
          resetTours(page);
          router.push(help.href!);
        }
      }}
    >
      {label}
    </Button>
  );
}

/** Every page's help, from the same source as the Help panel and the tours. */
export function PageGuides() {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {(Object.keys(PAGE_HELP) as PageId[]).map((id) => {
        const help = PAGE_HELP[id];
        return (
          <Card key={id} id={`page-${id}`} className="scroll-mt-20" aria-labelledby={`page-${id}-title`}>
            <div className="flex flex-wrap items-start justify-between gap-2 border-b border-line px-4 py-3">
              <div className="min-w-0">
                <h3 id={`page-${id}-title`} className="text-sm font-semibold text-fg">
                  {help.title}
                </h3>
                <p className="mt-0.5 text-xs text-muted">{help.summary}</p>
              </div>
              <TourLink page={id} />
            </div>
            <dl className="grid gap-2 px-4 py-3">
              {help.topics.map((t) => (
                <div key={t.title}>
                  <dt className="text-xs font-medium text-fg">{t.title}</dt>
                  <dd className="text-xs leading-relaxed text-muted">
                    <RichText text={t.body} />
                  </dd>
                </div>
              ))}
            </dl>
            {help.docs.length ? (
              <p className="flex flex-wrap gap-x-3 gap-y-1 border-t border-line px-4 py-2 text-xs">
                {help.docs.map((d) => (
                  <a key={d.path} href={docsUrl(d.path)} target="_blank" rel="noreferrer" className="text-muted hover:text-fg">
                    {d.label} ↗<span className="sr-only"> (opens in a new tab)</span>
                  </a>
                ))}
              </p>
            ) : null}
          </Card>
        );
      })}
    </div>
  );
}
