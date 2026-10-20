"use client";

import { Card } from "@/components/ui/Card";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import type { LedgerOut } from "@/lib/api/deals";
import { formatMoney } from "@/lib/format";

const th = "py-2 pr-3 text-left font-medium";
const td = "py-2 pr-3 align-top";

export function LedgerTable({ ledger }: { ledger: LedgerOut }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <Card as="section" labelledBy="ledger-h" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ledger-h" className="text-lg font-bold text-ink">
          {t("led.title")}
        </h2>
        <SimulatedBadge />
      </div>
      <p className="text-xs text-muted">
        {ledger.balanced ? "✓ " : "✕ "}
        {ledger.balanced ? t("led.balanced") : t("led.unbalanced")}
      </p>
      {ledger.rows.length === 0 ? (
        <p className="text-sm text-muted">{t("led.empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-176 text-sm" data-testid="ledger-table">
            <caption className="sr-only">{t("led.caption")}</caption>
            <thead>
              <tr className="border-b border-line text-muted">
                <th scope="col" className={th}>{t("led.kind")}</th>
                <th scope="col" className={th}>{t("led.milestone")}</th>
                <th scope="col" className={th}>{t("led.account")}</th>
                <th scope="col" className={th}>{t("led.direction")}</th>
                <th scope="col" className={`${th} text-right`}>{t("led.amount")}</th>
                <th scope="col" className={th}>{t("led.fx")}</th>
                <th scope="col" className={th}>{t("led.posted")}</th>
              </tr>
            </thead>
            <tbody>
              {ledger.rows.map((r) => (
                <tr key={r.id} className="border-b border-line last:border-0">
                  <th scope="row" className={`${td} text-left font-semibold`}>
                    {t(`led.kinds.${r.kind}`)}
                  </th>
                  <td className={td}>{r.milestone_seq ?? "—"}</td>
                  <td className={td}>{r.account}</td>
                  <td className={td}>{t(`led.dir.${r.direction}`)}</td>
                  <td className={`${td} text-right tabular-nums`}>
                    {formatMoney(r.amount, r.currency, lang)}
                  </td>
                  <td className={`${td} text-xs tabular-nums`}>
                    {r.fx_rate && r.counter_amount && r.counter_currency
                      ? t("led.fxDetail", {
                          rate: r.fx_rate,
                          amount: formatMoney(r.counter_amount, r.counter_currency, lang),
                        })
                      : "—"}
                  </td>
                  <td className={`${td} text-xs`}>
                    {new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-US", {
                      dateStyle: "medium",
                      timeStyle: "short",
                      timeZone: "Asia/Dhaka",
                    }).format(new Date(r.posted_at))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
