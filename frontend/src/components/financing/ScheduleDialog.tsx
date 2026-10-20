"use client";

import { Money } from "@/components/analysis/Money";
import { Modal } from "@/components/ui/Modal";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";
import { getSchedule, type OptionQuote } from "@/lib/api/financing";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Props = {
  option: OptionQuote;
  amount: string;
  dealId: string;
  partyId: string | undefined;
  currency: Currency;
  onClose: () => void;
};

export function ScheduleDialog({
  option,
  amount,
  dealId,
  partyId,
  currency,
  onClose,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const { data, error, reload } = useApi(
    (s) =>
      getSchedule(option.code, amount, option.start_on, dealId, partyId, s),
    `sched|${option.code}|${amount}|${dealId}|${partyId}`,
  );
  return (
    <Modal
      title={t("fin.schedule.title", { name: option.name })}
      onClose={onClose}
    >
      <div className="space-y-4">
        <SimulatedBadge />
        {error ? (
          <QueryError error={error} onRetry={reload} />
        ) : !data ? (
          <div aria-busy="true" className="space-y-2">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
          </div>
        ) : (
          <>
            <p className="text-sm text-muted">
              {t("fin.schedule.summary", {
                days: data.tenor_days,
                date: formatDate(data.maturity_on, lang),
              })}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">
                  {t("fin.schedule.caption")}
                </caption>
                <thead className="text-muted">
                  <tr>
                    <th scope="col" className="py-2 pr-4 font-medium">
                      {t("fin.schedule.due")}
                    </th>
                    <th scope="col" className="py-2 pr-4 font-medium">
                      {t("fin.schedule.principal")}
                    </th>
                    <th scope="col" className="py-2 pr-4 font-medium">
                      {t("fin.schedule.cost")}
                    </th>
                    <th scope="col" className="py-2 font-medium">
                      {t("fin.schedule.total")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.instalments.map((i) => (
                    <tr key={i.due_on} className="border-t border-line">
                      <th
                        scope="row"
                        className="py-2 pr-4 font-semibold text-ink"
                      >
                        {formatDate(i.due_on, lang)}
                      </th>
                      <td className="py-2 pr-4">
                        <Money amounts={i.principal} currency={currency} />
                      </td>
                      <td className="py-2 pr-4">
                        <Money amounts={i.cost} currency={currency} />
                      </td>
                      <td className="py-2 font-semibold">
                        <Money amounts={i.total} currency={currency} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-sm font-semibold text-ink">
              {t("fin.opt.total")}:{" "}
              <Money amounts={data.cost.total} currency={currency} />
            </p>
          </>
        )}
      </div>
    </Modal>
  );
}
