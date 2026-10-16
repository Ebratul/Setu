"use client";

import { Money } from "@/components/analysis/Money";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";
import type { Application } from "@/lib/api/financing";
import { formatDate } from "@/lib/format";

import { ApplicationStatusChip } from "./ApplicationStatusChip";

type Props = {
  applications: Application[] | undefined;
  error: unknown;
  onRetry: () => void;
  currency: Currency;
};

export function ApplicationsList({
  applications,
  error,
  onRetry,
  currency,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  return (
    <section aria-labelledby="fin-apps-h" className="space-y-3">
      <h2 id="fin-apps-h" className="text-lg font-bold text-ink">
        {t("fin.apps.title")}
      </h2>
      {error ? (
        <QueryError error={error} onRetry={onRetry} />
      ) : !applications ? (
        <Skeleton className="h-24" />
      ) : applications.length === 0 ? (
        <EmptyState title={t("fin.apps.empty")} />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <caption className="sr-only">{t("fin.apps.caption")}</caption>
            <thead className="text-muted">
              <tr>
                {["ref", "option", "amount", "total", "maturity", "status"].map(
                  (c) => (
                    <th key={c} scope="col" className="px-4 py-3 font-medium">
                      {t(`fin.apps.${c}`)}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {applications.map((a) => (
                <tr key={a.id} className="border-t border-line">
                  <th scope="row" className="px-4 py-3 font-semibold text-ink">
                    {a.reference}
                  </th>
                  <td className="px-4 py-3">{a.option_name}</td>
                  <td className="px-4 py-3">
                    <Money amounts={a.amount} currency={currency} />
                  </td>
                  <td className="px-4 py-3">
                    <Money amounts={a.total_cost} currency={currency} />
                  </td>
                  <td className="px-4 py-3">
                    {formatDate(a.maturity_on, lang)}
                  </td>
                  <td className="px-4 py-3">
                    <ApplicationStatusChip status={a.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </section>
  );
}
