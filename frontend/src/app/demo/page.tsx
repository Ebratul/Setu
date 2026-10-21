import type { Metadata } from "next";
import { Suspense } from "react";

import { DemoLanding } from "@/components/demo/DemoLanding";
import { loadEvalResults } from "@/lib/evalResults";

export const metadata: Metadata = {
  title: "Guided demo — Setu",
  description: "Watch the guided demo, start your own sandbox or open a playground. Simulated data only.",
  robots: { index: false, follow: false },
};

async function Landing() {
  const results = await loadEvalResults();
  return <DemoLanding results={results} />;
}

export default function DemoHubPage() {
  return (
    <Suspense fallback={null}>
      <Landing />
    </Suspense>
  );
}
