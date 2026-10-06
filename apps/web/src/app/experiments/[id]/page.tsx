import type { Metadata } from "next";

import { ExperimentSummary } from "@/components/experiment/experiment-summary";

export const metadata: Metadata = { title: "Experiment" };

export default async function ExperimentPage(props: PageProps<"/experiments/[id]">) {
  const { id } = await props.params;
  return <ExperimentSummary id={id} />;
}
