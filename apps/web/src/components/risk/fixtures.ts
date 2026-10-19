import type { RiskOut, TraceItem } from "@/lib/api/risk";

export const traceItem = (over: Partial<TraceItem> = {}): TraceItem => ({
  code: "AMOUNT_OVER_LIMIT",
  kind: "TIER3",
  fired: true,
  deciding: true,
  label_en: "Amount above the Tier 1 limit",
  label_bn: "পরিমাণ টিয়ার ১ সীমার বেশি",
  value_en: "Amount USD 22,000 vs limit USD 20,000",
  value_bn: "পরিমাণ USD ২২,০০০, সীমা USD ২০,০০০",
  ...over,
});

export const risk = (over: Partial<RiskOut> = {}): RiskOut => ({
  decision: "REQUIRE_APPROVAL",
  tier: 3,
  reasons: ["AMOUNT_OVER_LIMIT"],
  explanation_en: "Large payment needs OTP.",
  explanation_bn: "বড় পেমেন্টে OTP লাগবে।",
  context_hash: "abc",
  decided_by: ["AMOUNT_OVER_LIMIT"],
  trace: [
    traceItem(),
    traceItem({ code: "FIRST_DEAL", kind: "TIER2", fired: true, deciding: false, label_en: "First deal", value_en: "First deal: yes" }),
    traceItem({ code: "SANCTIONS", kind: "BLOCK", fired: false, deciding: false, label_en: "Sanctions hit", value_en: "No hit" }),
  ],
  hints: [{ code: "LOWER_AMOUNT", to_tier: 2, text_en: "Release in smaller tranches", text_bn: "ছোট কিস্তিতে ছাড় করুন" }],
  ...over,
});
