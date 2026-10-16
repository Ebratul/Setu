"use client";

import { useSearchParams } from "next/navigation";

import { Card } from "@/components/ui/Card";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import {
  formatDate,
  formatMoney,
  INPUT_DECIMAL,
  type Currency,
} from "@/lib/format";

export function FinancingPlaceholder() {
  const t = useT();
  const { lang } = useLang();
  const params = useSearchParams();
  const rawAmount = params.get("amount") ?? "";
  const rawDate = params.get("date") ?? "";
  const deal = params.get("deal");
  const rawCur = params.get("currency");
  const currency: Currency =
    rawCur === "BDT" || rawCur === "CNY" ? rawCur : "USD";
  const amount = INPUT_DECIMAL.test(rawAmount) ? rawAmount : null;
  const date = /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-ink">{t("fin.title")}</h1>
        <SimulatedBadge />
      </div>
      <Card className="space-y-2">
        {amount && date ? (
          <p className="text-lg font-semibold text-ink">
            {deal
              ? t("fin.need", {
                  amount: formatMoney(amount, currency, lang),
                  date: formatDate(date, lang),
                  deal,
                })
              : t("fin.needNoDeal", {
                  amount: formatMoney(amount, currency, lang),
                  date: formatDate(date, lang),
                })}
          </p>
        ) : (
          <p className="text-muted">{t("fin.noPrefill")}</p>
        )}
        <p className="text-sm text-muted">{t("fin.soon")}</p>
      </Card>
    </div>
  );
}
