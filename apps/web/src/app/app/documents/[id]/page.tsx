export const instant = false;

import { DocumentViewerPage } from "@/components/documents/DocumentViewerPage";

export default async function Page({ params }: PageProps<"/app/documents/[id]">) {
  const { id } = await params;
  return <DocumentViewerPage id={id} />;
}
