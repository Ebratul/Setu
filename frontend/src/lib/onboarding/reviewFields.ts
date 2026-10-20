import type { RevealableField, ReviewDetail } from "@/lib/api/onboarding";

import { flatten } from "./validate";

export type ReviewField = { key: string; value: string; reveal: RevealableField | null; zh?: boolean };

const REVEAL: Record<string, RevealableField> = {
  trade_license_no_masked: "trade_license_no",
  irc_no_masked: "irc_no",
  tin_masked: "tin",
  uscc_masked: "uscc",
  "bank.account_masked": "bank_account_no",
};

/** Flattens the masked business echo (and the contact mobile) into rows; masked rows say which field can be revealed. */
export function reviewFields(r: Pick<ReviewDetail, "business" | "contact">): ReviewField[] {
  const out: ReviewField[] = [];
  if (r.contact?.mobile_masked) out.push({ key: "mobile", value: r.contact.mobile_masked, reveal: "mobile" });
  for (const [k, v] of Object.entries(flatten(r.business))) {
    const base = k === "bank.account_masked" ? "bank.account_no" : k.replace(/_masked$/, "");
    out.push({ key: base, value: v, reveal: REVEAL[k] ?? null });
  }
  return out;
}
