"use client";

import { useLang } from "@/i18n";
import { formatMoney, type Currency } from "@/lib/format";

type Props = { value: string; currency: Currency };

export function DealMoney({ value, currency }: Props) {
  const { lang } = useLang();
  const text = formatMoney(value, currency, lang);
  return (
    <span title={currency} aria-label={`${text} ${currency}`}>
      {text}
    </span>
  );
}
