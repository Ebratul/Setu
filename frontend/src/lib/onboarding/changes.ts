import type { DocType } from "@/lib/api/onboarding";

import type { WizardStep } from "./steps";

const DOC_TYPES: readonly string[] = [
  "TRADE_LICENSE",
  "IRC",
  "TIN_CERT",
  "BUSINESS_LICENSE",
  "BANK_PROOF",
  "OTHER",
] satisfies DocType[];
const CONTACT = ["full_name", "designation", "mobile", "language"];

/** Which wizard step fixes a change-request target (a field key or a document type). */
export function stepForTarget(target: string): WizardStep {
  if (DOC_TYPES.includes(target)) return "documents";
  if (CONTACT.includes(target)) return "contact";
  if (target === "consent") return "security";
  return "business";
}

export const isDocTarget = (target: string) => DOC_TYPES.includes(target);
