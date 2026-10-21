"use client";

import { useLang } from "@/i18n";
import { formatMoney } from "@/lib/format";
import type { Amounts, Currency } from "@/lib/api/analysis";

type Props = { amounts: Amounts; currency: Currency };

/** Renders a server-converted amount with the ISO code as accessible name. */
export function Money({ amounts, currency }: Props) {
  const { lang } = useLang();
  const text = formatMoney(amounts[currency], currency, lang);
  return (
    <span title={currency} aria-label={`${text} ${currency}`}>
      {text}
    </span>
  );
}
