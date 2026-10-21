export const instant = false;

import { SupplierShell } from "@/components/supplier/SupplierShell";

export default function SupplierLayout({ children }: LayoutProps<"/supplier">) {
  return <SupplierShell>{children}</SupplierShell>;
}
