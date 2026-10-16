"use client";

import { Modal } from "@/components/ui/Modal";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT, pickLang } from "@/i18n";
import { getImpact, type FinMode, type OptionQuote } from "@/lib/api/financing";
import { formatDate, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { ExplanationList } from "./ExplanationList";
import { ImpactChart } from "./ImpactChart";

type Props = {
  option: OptionQuote;
  amount: string;
  mode: FinMode;
  dealId: string;
  partyId: string | undefined;
  onClose: () => void;
};

export function ImpactDialog({
  option,
  amount,
  mode,
  dealId,
  partyId,
  onClose,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const { data, error, reload } = useApi(
    (s) =>
      getImpact(
        {
          option_id: option.code,
          amount,
          mode,
          deal_id: dealId,
          party_id: partyId,
        },
        s,
      ),
    `impact|${option.code}|${amount}|${mode}|${dealId}|${partyId}`,
  );
  const summary = data
    ? data.explanations.map((e) => pickLang(e, lang)).join(" ")
    : "";
  return (
    <Modal title={t("fin.imp.title", { name: option.name })} onClose={onClose}>
      <div className="space-y-4">
        <SimulatedBadge />
        {error ? (
          <QueryError error={error} onRetry={reload} />
        ) : !data ? (
          <div aria-busy="true" className="space-y-2">
            <Skeleton className="h-56" />
            <Skeleton className="h-8" />
          </div>
        ) : (
          <>
            <ImpactChart impact={data} summary={summary} />
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted">{t("fin.imp.lowestBefore")}</dt>
                <dd className="font-semibold text-ink">
                  {formatMoney(data.before.lowest_balance, data.currency, lang)}{" "}
                  · {formatDate(data.before.lowest_on, lang)}
                </dd>
              </div>
              <div>
                <dt className="text-muted">{t("fin.imp.lowestAfter")}</dt>
                <dd className="font-semibold text-ink">
                  {formatMoney(data.after.lowest_balance, data.currency, lang)}{" "}
                  · {formatDate(data.after.lowest_on, lang)}
                </dd>
              </div>
            </dl>
            <div aria-live="polite">
              <ExplanationList items={data.explanations} />
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
