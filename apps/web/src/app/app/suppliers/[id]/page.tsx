import { SupplierProfilePage } from "@/components/kyb/SupplierProfilePage";

export default async function Page({
  params,
}: PageProps<"/app/suppliers/[id]">) {
  const { id } = await params;
  return <SupplierProfilePage id={id} />;
}
