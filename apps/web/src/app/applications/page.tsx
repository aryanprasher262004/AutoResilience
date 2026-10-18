import type { Metadata } from "next";

import { ApplicationsView } from "@/components/applications/applications-view";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Applications" };

export default function ApplicationsPage() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Namespace-scoped views of authorized clusters, with their live topology and experiment targets."
        actions={
          <ButtonLink href="/applications/new" variant="primary">
            Onboard application
          </ButtonLink>
        }
      />
      <ApplicationsView />
    </>
  );
}
