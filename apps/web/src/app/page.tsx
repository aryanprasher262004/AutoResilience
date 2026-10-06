import type { Metadata } from "next";

import { OverviewDashboard } from "@/components/overview/overview-dashboard";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Overview" };

export default function OverviewPage() {
  return (
    <>
      <PageHeader
        title="Overview"
        description="Outcomes, scores and recovery across every recorded experiment."
        actions={<ButtonLink href="/experiments">Experiment history</ButtonLink>}
      />
      <OverviewDashboard />
    </>
  );
}
