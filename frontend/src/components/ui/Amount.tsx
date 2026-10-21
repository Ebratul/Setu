"use client";

import { useLang } from "@/i18n";
import { formatMoney, type Currency } from "@/lib/format";

const NAMES: Record<Currency, string> = {
  BDT: "Bangladeshi taka",
  USD: "US dollar",
  CNY: "Chinese yuan (renminbi)",
};

type Props = { value: string; currency: Currency; className?: string };

/** Server decimal string -> localised money. Never parses to float; ISO code on hover and for screen readers. */
export function Amount({ value, currency, className = "" }: Props) {
  const { lang } = useLang();
  const text = formatMoney(value, currency, lang);
  return (
    <span
      title={currency}
      aria-label={`${text} ${NAMES[currency]}`}
      className={`tabular-nums ${className}`}
    >
      <span aria-hidden="true">{text}</span>
    </span>
  );
}
