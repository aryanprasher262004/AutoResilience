import type { Metadata } from "next";

import { AboutOnboarding } from "@/components/applications/about-onboarding";
import { ApplicationsView } from "@/components/applications/applications-view";
import { ButtonLink } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { TOUR_TARGET } from "@/lib/help-content";

export const metadata: Metadata = { title: "Applications" };

export default function ApplicationsPage() {
  return (
    <>
      <PageHeader
        title="Applications"
        description="Namespace-scoped views of authorized clusters, with their live topology and experiment targets."
        actions={
          <ButtonLink href="/applications/new" variant="primary" data-tour={TOUR_TARGET.applicationsOnboard}>
            Onboard application
          </ButtonLink>
        }
      />
      <div className="grid gap-4">
        <AboutOnboarding />
        <ApplicationsView />
      </div>
    </>
  );
}
