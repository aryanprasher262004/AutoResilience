import type { Metadata } from "next";
import { Suspense } from "react";

import { ServicesView } from "@/components/services/services-view";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { LoadingState } from "@/components/ui/states";

export const metadata: Metadata = { title: "Services" };

export default function ServicesPage() {
  return (
    <>
      <PageHeader
        title="Services"
        description="Deployments and StatefulSets discovered in the cluster, with their live health and resilience history."
      />
      {/* useSearchParams needs a Suspense boundary on statically rendered routes. */}
      <Suspense fallback={<Card><LoadingState rows={6} label="Discovering workloads" /></Card>}>
        <ServicesView />
      </Suspense>
    </>
  );
}
