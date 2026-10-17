import { DealDetailPage } from "@/components/deals/DealDetailPage";

export default async function Page({ params }: PageProps<"/app/deals/[id]">) {
  const { id } = await params;
  return <DealDetailPage reference={id} />;
}
