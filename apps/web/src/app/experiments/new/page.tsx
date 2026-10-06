import type { Metadata } from "next";

import { ExperimentBuilder } from "@/components/experiment/builder/experiment-builder";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "New Experiment" };

export default function NewExperimentPage() {
  return (
    <>
      <PageHeader
        title="New Experiment"
        description="Configure a controlled pod-delete, let the server check it, then start it."
      />
      <ExperimentBuilder />
    </>
  );
}
