import type { Metadata } from "next";

import { ReportView } from "@/components/report/report-view";

export const metadata: Metadata = { title: "Report" };

export default async function ReportPage(props: PageProps<"/reports/[id]">) {
  const { id } = await props.params;
  return <ReportView id={id} />;
}
