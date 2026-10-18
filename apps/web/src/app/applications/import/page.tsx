import type { Metadata } from "next";

import { ImportWizard } from "@/components/imports/import-wizard";
import { PageHeader } from "@/components/ui/page-header";

export const metadata: Metadata = { title: "Import application" };

export default function ImportApplicationPage() {
  return (
    <>
      <PageHeader
        title="Import an application"
        description="Review a Compose file, manifests or an image as an isolated test deployment. Nothing is deployed until you approve its plan."
      />
      <ImportWizard />
    </>
  );
}
