import type { Metadata } from "next";

import { ApiStatus } from "@/components/shell/api-status";
import { ButtonLink } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { PlannedState } from "@/components/ui/states";

export const metadata: Metadata = { title: "Overview" };

export default function OverviewPage() {
  return (
    <>
      <PageHeader
        title="Overview"
        description="Controlled pod-delete experiments with measured recovery and an explainable Resilience Score."
        actions={<ButtonLink href="/experiments">View experiments</ButtonLink>}
      />
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Backend" description="Live reachability of the AutoResilience API" />
          <CardBody>
            <ApiStatus />
          </CardBody>
        </Card>
        <div className="lg:col-span-2">
          <PlannedState milestone="Planned · next milestones" title="Overview dashboard">
            <p>
              Will summarise real experiment outcomes from the API: recent runs and their
              states, score trends and services that failed to recover. Nothing is shown here
              until it can be computed from recorded experiments.
            </p>
          </PlannedState>
        </div>
      </div>
    </>
  );
}
