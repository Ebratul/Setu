export type Currency = "USD" | "BDT" | "CNY";
export type FormatLang = "en" | "bn";

const SYMBOL: Record<Currency, string> = { USD: "$", BDT: "৳", CNY: "¥" };

function locale(lang: FormatLang) {
  return lang === "bn" ? "bn-BD" : "en-US";
}

type NumericString = `${number}`;

/** Formats a server decimal string; the string goes straight to Intl (no float parsing). */
export function formatDecimal(
  value: string,
  lang: FormatLang = "en",
  maxFraction = 4,
): string {
  return new Intl.NumberFormat(locale(lang), {
    minimumFractionDigits: 2,
    maximumFractionDigits: maxFraction,
  }).format(value as NumericString);
}

export function formatMoney(
  value: string,
  currency: Currency,
  lang: FormatLang = "en",
): string {
  const negative = value.startsWith("-");
  const body = formatDecimal(negative ? value.slice(1) : value, lang);
  return `${negative ? "-" : ""}${SYMBOL[currency]}${body}`;
}

export function formatPct(value: string, lang: FormatLang = "en"): string {
  return `${formatDecimal(value, lang, 2)}%`;
}

export function formatSigned(value: string, lang: FormatLang = "en"): string {
  const body = formatDecimal(value.replace(/^[-+]/, ""), lang, 2);
  if (value.startsWith("-")) return `-${body}`;
  return /^[+]?0+(\.0+)?$/.test(value) ? body : `+${body}`;
}

export function formatDate(iso: string, lang: FormatLang = "en"): string {
  return new Intl.DateTimeFormat(locale(lang), {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${iso}T00:00:00Z`));
}

export function formatMonth(ym: string, lang: FormatLang = "en"): string {
  return new Intl.DateTimeFormat(locale(lang), {
    year: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(`${ym}-01T00:00:00Z`));
}

/** Client-side input-format check only (mirrors the API pattern); never used for arithmetic. */
export const INPUT_DECIMAL = /^\d{1,14}(\.\d{1,4})?$/;
