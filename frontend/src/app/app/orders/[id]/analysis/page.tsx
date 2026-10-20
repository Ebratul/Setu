export const instant = false;

import { OrderAnalysisPage } from "@/components/analysis/OrderAnalysisPage";

export default async function Page({
  params,
}: PageProps<"/app/orders/[id]/analysis">) {
  const { id } = await params;
  return <OrderAnalysisPage reference={id} />;
}
