import type { Metadata } from "next";
import dynamic from "next/dynamic";

import { FinalCta } from "@/components/landing/FinalCta";
import { Features } from "@/components/landing/Features";
import { Hero } from "@/components/landing/Hero";
import { Impact } from "@/components/landing/Impact";
import { LandingHeader } from "@/components/landing/LandingHeader";
import { Problem } from "@/components/landing/Problem";
import { PublicFooter } from "@/components/landing/PublicFooter";
import { ResultsBand } from "@/components/landing/ResultsBand";
import { SecurityBand } from "@/components/landing/SecurityBand";
import { loadEvalResults } from "@/lib/evalResults";

const HowItWorks = dynamic(() => import("@/components/landing/HowItWorks").then((m) => m.HowItWorks));
const Testimonials = dynamic(() => import("@/components/landing/Testimonials").then((m) => m.Testimonials));

const TITLE = "Setu সেতু — LC-grade protection for small importers";
const DESCRIPTION =
  "Milestone escrow, document forensics and risk-tiered human approval for Bangladeshi SMEs that import from Chinese suppliers. Simulated sandbox with fictional data.";

export const metadata: Metadata = {
  title: { absolute: TITLE },
  description: DESCRIPTION,
  alternates: { canonical: "/" },
  openGraph: { type: "website", url: "/", title: TITLE, description: DESCRIPTION, siteName: "Setu সেতু" },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION },
};

async function cachedResults() {
  "use cache";
  return loadEvalResults();
}

export default async function Home() {
  const results = await cachedResults();
  return (
    <>
      <LandingHeader />
      <main id="main" className="flex-1">
        <Hero />
        <Problem />
        <HowItWorks />
        <Features />
        <SecurityBand />
        <Impact />
        <ResultsBand results={results} />
        <Testimonials />
        <FinalCta />
      </main>
      <PublicFooter />
    </>
  );
}
