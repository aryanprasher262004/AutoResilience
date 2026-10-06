import type { Metadata } from "next";
import { Suspense } from "react";

import { HistoryView } from "@/components/history/history-view";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingState } from "@/components/ui/states";

export const metadata: Metadata = { title: "Experiments" };

export default function ExperimentsPage() {
  return (
    <>
      <PageHeader
        title="Experiments"
        description="History of every experiment recorded by the backend. Filters, sorting and paging run on the server."
        actions={
          <ButtonLink href="/experiments/new" variant="primary">
            New Experiment
          </ButtonLink>
        }
      />
      {/* useSearchParams needs a Suspense boundary on statically rendered routes. */}
      <Suspense fallback={<Card><LoadingState rows={6} label="Loading experiments" /></Card>}>
        <HistoryView mode="history" />
      </Suspense>
    </>
  );
}
