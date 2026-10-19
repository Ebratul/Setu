import type { Lang } from "@/i18n";
import type { Approval } from "@/lib/api/approvals";

export const pickLang = (lang: Lang, en: string, bn: string) => (lang === "bn" && bn ? bn : en);

export const actionLabel = (a: Approval, lang: Lang) =>
  pickLang(lang, a.action_label_en, a.action_label_bn);
export const whatHappens = (a: Approval, lang: Lang) =>
  pickLang(lang, a.what_happens_en, a.what_happens_bn);

export const isEmailOnly = (a: Approval) =>
  a.requested_via === "email" || a.blocked_reason === "EMAIL_ORIGIN";

export const prettyCode = (s: string) => s.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());

/** "2 h 5 min" style duration for expiry; locale-neutral digits. */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s >= 86400) return `${Math.floor(s / 86400)} d ${Math.floor((s % 86400) / 3600)} h`;
  if (s >= 3600) return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
  if (s >= 60) return `${Math.floor(s / 60)} min`;
  return `${s} s`;
}
