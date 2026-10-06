import type { Metadata } from "next";
import { Suspense } from "react";

import { HistoryView } from "@/components/history/history-view";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingState } from "@/components/ui/states";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  return (
    <>
      <PageHeader
        title="Reports"
        description="Evidence-backed reports for every finished experiment: safety, baseline, fault, impact, recovery and score."
      />
      <Suspense fallback={<Card><LoadingState rows={6} label="Loading reports" /></Card>}>
        <HistoryView mode="reports" />
      </Suspense>
    </>
  );
}
