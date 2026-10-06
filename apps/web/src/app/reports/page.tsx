import type { Metadata } from "next";

import { PageHeader } from "@/components/ui/page-header";
import { PlannedState } from "@/components/ui/states";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  return (
    <>
      <PageHeader title="Reports" description="Evidence-backed results of finished experiments." />
      <PlannedState milestone="Planned · later milestone" title="Experiment reports">
        <p>
          Will render the recorded evidence of finished experiments (validation, baseline,
          Litmus verdict, client-observed outage, recovery timing and the Resilience Score
          breakdown) as a shareable report.
        </p>
      </PlannedState>
    </>
  );
}
