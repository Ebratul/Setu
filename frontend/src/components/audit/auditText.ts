import type { Lang } from "@/i18n";

export const shortHash = (h: string, n = 8) => h.slice(0, n);

/** text_bn for Bangla; zh falls back to English. */
export const entryText = (e: { text_en: string; text_bn: string }, lang: Lang) => (lang === "bn" ? e.text_bn : e.text_en);

export function fmtTime(ts: string, lang: Lang): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : lang === "zh" ? "zh-CN" : "en-US", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "Asia/Dhaka",
  }).format(d);
}

const REASONS = ["hash_mismatch", "bad_signature", "missing_seq", "reordered", "broken_link", "malformed"];
export const reasonKey = (reason: string | null) =>
  reason && REASONS.includes(reason) ? `audit.reason.${reason}` : "audit.reason.unknown";
