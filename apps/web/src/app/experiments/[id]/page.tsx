import type { Metadata } from "next";

import { ExperimentRoom } from "@/components/experiment/room/experiment-room";

export const metadata: Metadata = { title: "Experiment" };

export default async function ExperimentPage(props: PageProps<"/experiments/[id]">) {
  const { id } = await props.params;
  return <ExperimentRoom id={id} />;
}
