export type Currency = "USD" | "BDT" | "CNY";
export type FormatLang = "en" | "bn" | "zh";

const SYMBOL: Record<Currency, string> = { USD: "$", BDT: "৳", CNY: "¥" };

export type DigitsPref = "native" | "latin";
export const DIGITS_KEY = "setu_digits";
export const DIGITS_EVENT = "setu-digits";

let digits: DigitsPref = "native";
const digitListeners = new Set<() => void>();

export function getDigits(): DigitsPref {
  return digits;
}

function emitDigits() {
  digitListeners.forEach((l) => l());
  if (typeof window !== "undefined") window.dispatchEvent(new Event(DIGITS_EVENT));
}

/** Sets the Bangla digit style (bn only; en/zh are unaffected) and persists it. */
export function setDigits(next: DigitsPref) {
  digits = next;
  try {
    localStorage.setItem(DIGITS_KEY, next);
  } catch {
    /* storage unavailable */
  }
  emitDigits();
}

/** Reads the stored preference once on the client; call from an effect to avoid hydration mismatch. */
export function loadDigits() {
  try {
    const v = localStorage.getItem(DIGITS_KEY);
    if ((v === "latin" || v === "native") && v !== digits) {
      digits = v;
      emitDigits();
    }
  } catch {
    /* storage unavailable */
  }
}

export function subscribeDigits(cb: () => void) {
  digitListeners.add(cb);
  return () => {
    digitListeners.delete(cb);
  };
}

function locale(lang: FormatLang) {
  if (lang === "bn") return digits === "latin" ? "bn-BD-u-nu-latn" : "bn-BD";
  return lang === "zh" ? "zh-CN" : "en-US";
}

type NumericString = `${number}`;

/** Formats a server decimal string; the string goes straight to Intl (no float parsing). */
export function formatDecimal(
  value: string,
  lang: FormatLang = "en",
  maxFraction = 4,
): string {
  return new Intl.NumberFormat(locale(lang), {
    minimumFractionDigits: Math.min(2, maxFraction),
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

export function formatDay(iso: string, lang: FormatLang = "en"): string {
  return new Intl.DateTimeFormat(locale(lang), {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${iso}T00:00:00Z`));
}
