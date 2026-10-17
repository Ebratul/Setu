import { SupplierOrderPage } from "@/components/supplier/SupplierOrderPage";

export default async function Page({ params }: PageProps<"/supplier/[id]">) {
  const { id } = await params;
  return <SupplierOrderPage reference={id} />;
}
