import type { Metadata } from "next";

import { AccessibilityStatement } from "@/components/landing/AccessibilityStatement";

const TITLE = "Accessibility statement — Setu";
const DESCRIPTION =
  "Setu targets WCAG 2.2 AA. What we have checked, what is still pending, keyboard shortcuts and known limitations.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: "/accessibility" },
  openGraph: { type: "website", url: "/accessibility", title: TITLE, description: DESCRIPTION },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION },
};

export default function AccessibilityPage() {
  return <AccessibilityStatement />;
}
