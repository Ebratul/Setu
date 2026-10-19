import type { Lang } from "@/i18n";

/** Picks the Bengali text for `bn`, English otherwise (zh falls back to English). */
export function pick(lang: Lang, en: string, bn: string): string {
  return lang === "bn" && bn ? bn : en;
}

/** Whole-number display for counts and thresholds (not money). */
export function fmtInt(n: number | string, lang: Lang): string {
  const loc = lang === "bn" ? "bn-BD" : lang === "zh" ? "zh-CN" : "en-US";
  return new Intl.NumberFormat(loc, { maximumFractionDigits: 0 }).format(Number(n));
}
