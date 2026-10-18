import type { Metadata } from "next";

import { AboutOnboarding } from "@/components/applications/about-onboarding";
import { Onboarding } from "@/components/applications/onboarding";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Onboard application" };

export default function OnboardApplicationPage() {
  return (
    <>
      <PageHeader
        title="Onboard a Kubernetes application"
        description="Read-only: choose a cluster and namespaces, inspect what runs there, then pick experiment targets."
      />
      <div className="grid gap-4">
        <AboutOnboarding defaultOpen={false} />
        <Onboarding />
      </div>
    </>
  );
}
