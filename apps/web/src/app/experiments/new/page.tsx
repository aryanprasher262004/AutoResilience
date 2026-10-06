import type { Metadata } from "next";

import { PageHeader } from "@/components/ui/page-header";
import { PlannedState } from "@/components/ui/states";

export const metadata: Metadata = { title: "New Experiment" };

export default function NewExperimentPage() {
  return (
    <>
      <PageHeader title="New Experiment" description="Define a controlled pod-delete experiment." />
      <PlannedState milestone="Planned · next milestone" title="Experiment builder">
        <p>
          Will create an experiment (target namespace, workload, affected replicas, duration,
          GRACEFUL or FORCE deletion) and start it automatically. The backend already supports
          this: <code className="font-mono">POST /experiments</code> then{" "}
          <code className="font-mono">POST /experiments/&#123;id&#125;/run</code>.
        </p>
        <p>
          Safety validation stays on the server: the selected namespace decides the safety policy,
          and system namespaces are always refused.
        </p>
      </PlannedState>
    </>
  );
}
