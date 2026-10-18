import type { Metadata } from "next";

import { AboutOnboarding } from "@/components/applications/about-onboarding";
import { ApplicationsView } from "@/components/applications/applications-view";
import { ImportEntry } from "@/components/imports/import-wizard";
import { ImportsList } from "@/components/imports/imports-list";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { TOUR_TARGET } from "@/lib/help-content";

export const metadata: Metadata = { title: "Applications" };

export default function ApplicationsPage() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Namespace-scoped views of authorized clusters, with their live topology and experiment targets. Onboard what already runs, or import an application as an isolated test deployment."
        actions={
          <>
            <ImportEntry />
            <ButtonLink href="/applications/new" variant="primary" data-tour={TOUR_TARGET.applicationsOnboard}>
              Onboard application
            </ButtonLink>
          </>
        }
      />
      <div className="grid gap-4">
        <AboutOnboarding />
        <ApplicationsView />
        <ImportsList />
      </div>
    </>
  );
}
