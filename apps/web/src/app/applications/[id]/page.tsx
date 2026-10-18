import type { Metadata } from "next";

import { ApplicationRoom } from "@/components/applications/application-room";

export const metadata: Metadata = { title: "Application" };

export default async function ApplicationPage(props: PageProps<"/applications/[id]">) {
  const { id } = await props.params;
  return <ApplicationRoom id={decodeURIComponent(id)} />;
}
