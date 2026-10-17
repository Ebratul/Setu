export const instant = false;

import { redirect } from "next/navigation";

export default function Page() {
  redirect("/app/deals");
}
