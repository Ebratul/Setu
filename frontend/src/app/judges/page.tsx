import type { Metadata } from "next";

import { JudgesPage } from "@/components/judges/JudgesPage";
import { PublicFooter } from "@/components/landing/PublicFooter";
import { PublicHeader } from "@/components/landing/PublicHeader";

const TITLE = "Judge quick-start — Setu";
const DESCRIPTION =
  "Review Setu in minutes: private sandbox, 60-second tour, features mapped to requirements, QR codes and live system status. Simulated sandbox with fictional data.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: "/judges" },
  openGraph: {
    type: "website",
    url: "/judges",
    title: TITLE,
    description: DESCRIPTION,
    siteName: "Setu সেতু",
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
  },
};

export default function JudgesRoute() {
  return (
    <>
      <PublicHeader />
      <main id="main" className="flex-1">
        <JudgesPage />
      </main>
      <PublicFooter />
    </>
  );
}
