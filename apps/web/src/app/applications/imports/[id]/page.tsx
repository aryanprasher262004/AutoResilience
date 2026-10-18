import type { Metadata } from "next";

import { ImportRoom } from "@/components/imports/import-room";

export const metadata: Metadata = { title: "Imported application" };

export default async function ImportPage(props: PageProps<"/applications/imports/[id]">) {
  const { id } = await props.params;
  return <ImportRoom id={decodeURIComponent(id)} />;
}
