"use client";

import { Card } from "@/components/ui/Card";
import { hasKey, useLang, useT } from "@/i18n";
import type { Day } from "@/lib/api/cashflow";
import { formatDate, formatMoney, type Currency } from "@/lib/format";

type Props = { day: Day | undefined; currency: Currency };

export function DayDetails({ day, currency }: Props) {
  const t = useT();
  const { lang } = useLang();
  const money = (v: string) => formatMoney(v, currency, lang);
  return (
    <Card as="section" labelledBy="day-h" className="space-y-3">
      <div aria-live="polite">
        <h3 id="day-h" className="text-lg font-semibold text-ink">
          {day
            ? t("cf.dayDetails", { date: formatDate(day.on, lang) })
            : t("cf.dayDetailsNone")}
        </h3>
        {day ? (
          <>
            <p className="text-sm text-muted">
              {t("cf.openingClosing", {
                opening: money(day.opening),
                closing: money(day.closing),
              })}
            </p>
            {day.below_buffer ? (
              <p className="mt-1 text-sm font-semibold text-danger">
                ▼ {t("cf.belowBuffer")}
              </p>
            ) : null}
            {day.items.length === 0 ? (
              <p className="mt-2 text-sm text-muted">{t("cf.noItems")}</p>
            ) : (
              <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-80 text-sm">
                  <caption className="sr-only">{t("cf.itemsCaption")}</caption>
                  <thead>
                    <tr className="border-b border-line text-left text-muted">
                      <th scope="col" className="py-1 font-medium">
                        {t("cf.item")}
                      </th>
                      <th scope="col" className="py-1 font-medium">
                        {t("cf.kind")}
                      </th>
                      <th scope="col" className="py-1 font-medium">
                        {t("cf.direction")}
                      </th>
                      <th scope="col" className="py-1 text-right font-medium">
                        {t("cf.amount")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {day.items.map((i) => (
                      <tr
                        key={i.ref}
                        className="border-b border-line last:border-0"
                      >
                        <th
                          scope="row"
                          className="py-1 pr-2 text-left font-medium"
                        >
                          {i.label}
                        </th>
                        <td className="py-1 pr-2">
                          {hasKey(`flow.kind.${i.kind}`)
                            ? t(`flow.kind.${i.kind}`)
                            : i.kind}
                        </td>
                        <td className="py-1 pr-2">
                          {i.direction === "IN" ? "↓ " : "↑ "}
                          {t(`cf.dir.${i.direction}`)}
                        </td>
                        <td className="py-1 text-right tabular-nums">
                          {money(i.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : (
          <p className="text-sm text-muted">{t("cf.dayDetailsHint")}</p>
        )}
      </div>
    </Card>
  );
}
