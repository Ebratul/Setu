import { redirect } from "next/navigation";

export default async function Page({ params }: PageProps<"/app/orders/[id]">) {
  const { id } = await params;
  redirect(`/app/deals/${encodeURIComponent(id)}`);
}
