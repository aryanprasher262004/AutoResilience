import type { Metadata } from "next";

import { PageHeader } from "@/components/ui/page-header";
import { PlannedState } from "@/components/ui/states";

export const metadata: Metadata = { title: "Services" };

export default function ServicesPage() {
  return (
    <>
      <PageHeader title="Services" description="Workloads that can be targeted by experiments." />
      <PlannedState milestone="Planned · needs a backend endpoint" title="Service inventory">
        <p>
          The backend can inspect a single target during validation, but it does not yet expose
          a list of candidate workloads. This page will list Deployments and StatefulSets per
          namespace, with their last experiment result, once that read-only endpoint exists.
        </p>
      </PlannedState>
    </>
  );
}
