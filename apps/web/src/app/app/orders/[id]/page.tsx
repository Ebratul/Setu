import { OrderDetail } from "@/components/analysis/OrderDetail";

export default async function Page({ params }: PageProps<"/app/orders/[id]">) {
  const { id } = await params;
  return <OrderDetail reference={id} />;
}
