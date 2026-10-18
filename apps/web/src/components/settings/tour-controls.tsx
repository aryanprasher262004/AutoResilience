"use client";

import { useRouter } from "next/navigation";

import { startTour } from "@/components/tour/tour-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";
import { PAGE_HELP, TOUR_PAGES, TOUR_TARGET } from "@/lib/help-content";
import { resetTours, useHydrated, usePreferences } from "@/lib/preferences";

/** Per-page tour progress (this browser): replay one now, or reset so it opens on the next visit. */
export function TourControls() {
  const router = useRouter();
  const hydrated = useHydrated();
  const tours = usePreferences().tours;
  const any = Object.keys(tours).length > 0;
  return (
    <Card data-tour={TOUR_TARGET.settingsTours}>
      <CardHeader
        level={3}
        title="Guided tours"
        description="Each page's tour opens on your first visit and is remembered in this browser once finished or skipped."
        actions={
          <Button size="sm" variant="ghost" disabled={!hydrated || !any} onClick={() => resetTours()}>
            Reset all
          </Button>
        }
      />
      <ul className="divide-y divide-line" aria-label="Page tours">
        {TOUR_PAGES.map((page) => {
          const help = PAGE_HELP[page];
          const record = tours[page];
          return (
            <li key={page} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <p className="text-sm text-fg">{help.title}</p>
                <p className="text-2xs text-faint">
                  {help.tour!.length} steps ·{" "}
                  {!hydrated
                    ? "checking…"
                    : record
                      ? `${record.status === "completed" ? "finished" : "skipped"} ${formatDateTime(record.at)}`
                      : help.href
                        ? "opens on your next visit"
                        : "opens the next time you open an application"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {hydrated ? (
                  <Badge tone={record ? (record.status === "completed" ? "success" : "neutral") : "info"}>
                    {record ? (record.status === "completed" ? "Finished" : "Skipped") : "Not seen"}
                  </Badge>
                ) : null}
                <Button size="sm" variant="ghost" disabled={!record} onClick={() => resetTours(page)}>
                  Reset
                </Button>
                {help.href ? (
                  <Button
                    size="sm"
                    onClick={() => {
                      if (page === "settings") startTour(page);
                      else {
                        resetTours(page);
                        router.push(help.href!);
                      }
                    }}
                  >
                    Replay
                  </Button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
