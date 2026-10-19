import type { Lang } from "@/i18n";
import { orderedCounts } from "@/lib/privacy/segments";

type T = (key: string, vars?: Record<string, string | number>) => string;

const LOCALE: Record<Lang, string> = { en: "en-US", bn: "bn-BD", zh: "zh-CN" };

export function fmtNum(n: number, lang: Lang): string {
  return new Intl.NumberFormat(LOCALE[lang]).format(n);
}

function plural(lang: Lang, n: number): "one" | "other" {
  return new Intl.PluralRules(LOCALE[lang]).select(n) === "one" ? "one" : "other";
}

/** Localised type name, falling back to the raw code for unknown types. */
export function typeLabel(t: T, type: string, n: number, lang: Lang = "en"): string {
  const key = `privacy.type.${type}.${plural(lang, n)}`;
  const out = t(key);
  return out === key ? type : out;
}

/** "3 identifiers protected: 1 account, 1 phone number, 1 NID" */
export function countsLine(
  t: T,
  lang: Lang,
  byType: Record<string, number>,
  total: number,
): string {
  if (total <= 0) return t("privacy.summary.none");
  const list = orderedCounts(byType)
    .map(([type, n]) => `${fmtNum(n, lang)} ${typeLabel(t, type, n, lang)}`)
    .join(", ");
  return t(`privacy.summary.${plural(lang, total)}`, { n: fmtNum(total, lang), list });
}
