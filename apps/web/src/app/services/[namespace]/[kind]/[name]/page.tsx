import type { Metadata } from "next";

import { ServiceDetailView } from "@/components/services/service-detail";

export const metadata: Metadata = { title: "Service" };

export default async function ServicePage(props: PageProps<"/services/[namespace]/[kind]/[name]">) {
  const { namespace, kind, name } = await props.params;
  return (
    <ServiceDetailView
      namespace={decodeURIComponent(namespace)}
      kind={decodeURIComponent(kind)}
      name={decodeURIComponent(name)}
    />
  );
}
