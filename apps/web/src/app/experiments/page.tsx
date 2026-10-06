import type { Metadata } from "next";

import { ExperimentsTable } from "@/components/experiment/experiments-table";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Experiments" };

export default function ExperimentsPage() {
  return (
    <>
      <PageHeader
        title="Experiments"
        description="Every experiment recorded by the backend, with its live lifecycle state."
        actions={
          <ButtonLink href="/experiments/new" variant="primary">
            New Experiment
          </ButtonLink>
        }
      />
      <ExperimentsTable />
    </>
  );
}
