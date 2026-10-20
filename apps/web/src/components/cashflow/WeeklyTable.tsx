"use client";

import { useLang, useT } from "@/i18n";
import type { Forecast } from "@/lib/api/cashflow";
import { formatDate, formatMoney, type Currency } from "@/lib/format";

type Props = { forecast: Forecast };

export function WeeklyTable({ forecast }: Props) {
  const t = useT();
  const { lang } = useLang();
  const cur = forecast.currency as Currency;
  const money = (v: string) => formatMoney(v, cur, lang);
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer font-semibold text-brand-text focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
        {t("cf.showWeekly")}
      </summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-120">
          <caption className="sr-only">{t("cf.weeklyCaption")}</caption>
          <thead>
            <tr className="border-b border-line text-left text-muted">
              <th scope="col" className="py-1 font-medium">
                {t("cf.week")}
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                {t("cf.inflow")}
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                {t("cf.outflow")}
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                {t("cf.closing")}
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                {t("cf.lowest")}
              </th>
            </tr>
          </thead>
          <tbody>
            {forecast.weekly.map((w) => (
              <tr key={w.start} className="border-b border-line last:border-0">
                <th scope="row" className="py-1 text-left font-medium">
                  {formatDate(w.start, lang)} – {formatDate(w.end, lang)}
                </th>
                <td className="py-1 text-right tabular-nums">
                  {money(w.inflow)}
                </td>
                <td className="py-1 text-right tabular-nums">
                  {money(w.outflow)}
                </td>
                <td className="py-1 text-right tabular-nums">
                  {money(w.closing)}
                </td>
                <td className="py-1 text-right tabular-nums">
                  {money(w.lowest)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
