import type { Metadata } from "next";
import { Suspense } from "react";

import { DemoRunPage } from "@/components/demo/DemoRunPage";

export const metadata: Metadata = {
  title: "Guided demo — Setu",
  description: "Walk the whole Setu story in about four minutes. Simulated sandbox, fictional data.",
  robots: { index: false, follow: false },
};

export default function DemoRunRoute() {
  return (
    <Suspense fallback={null}>
      <DemoRunPage />
    </Suspense>
  );
}
