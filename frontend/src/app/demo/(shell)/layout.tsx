export const instant = false;

import { AppShell } from "@/components/shell/AppShell";

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
