"use client";

import Link from "next/link";

import { useLang } from "@/i18n";
import type { Currency, MonthlySummary } from "@/lib/api/analysis";
import { formatPct } from "@/lib/format";

import { Money } from "./Money";

type Props = {
  deal: MonthlySummary["deals"][number];
  currency: Currency;
};

export function DealLinkRow({ deal, currency }: Props) {
  const { lang } = useLang();
  return (
    <tr className="border-b border-line last:border-0">
      <th scope="row" className="py-2 text-left font-semibold">
        <Link
          href={`/app/orders/${deal.reference}/analysis`}
          className="text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        >
          {deal.reference}
        </Link>
      </th>
      <td className="py-2">{deal.supplier_name}</td>
      <td className="py-2 text-right tabular-nums">
        <Money amounts={deal.landed_cost} currency={currency} />
      </td>
      <td className="py-2 text-right tabular-nums">
        {deal.gross_margin_pct ? formatPct(deal.gross_margin_pct, lang) : "—"}
      </td>
    </tr>
  );
}
