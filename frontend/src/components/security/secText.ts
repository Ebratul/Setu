import type { Lang } from "@/i18n";

/** Bengali text for `bn`, English otherwise (the API only ships en and bn; zh falls back to en). */
export function pickText(lang: Lang, en: string, bn: string): string {
  return lang === "bn" && bn ? bn : en;
}

export function fmtPct(x: number, lang: Lang): string {
  const loc = lang === "bn" ? "bn-BD" : lang === "zh" ? "zh-CN" : "en-US";
  return new Intl.NumberFormat(loc, { style: "percent", maximumFractionDigits: 1 }).format(x);
}

export function fmtN(n: number, lang: Lang): string {
  const loc = lang === "bn" ? "bn-BD" : lang === "zh" ? "zh-CN" : "en-US";
  return new Intl.NumberFormat(loc).format(n);
}

export function fmtDateTime(iso: string, lang: Lang): string {
  const loc = lang === "bn" ? "bn-BD" : lang === "zh" ? "zh-CN" : "en-GB";
  return new Intl.DateTimeFormat(loc, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(iso)) + " UTC";
}
