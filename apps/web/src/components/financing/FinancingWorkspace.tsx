"use client";

import { useState } from "react";

import { CurrencyToggle } from "@/components/analysis/CurrencyToggle";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";
import {
  getGap,
  listApplications,
  matchOptions,
  type FinMode,
  type OptionQuote,
} from "@/lib/api/financing";
import { useApi, useDebounced } from "@/lib/useApi";

import { AmountControls, isValidAmount } from "./AmountControls";
import { ApplicationsList } from "./ApplicationsList";
import { ApplyDialog } from "./ApplyDialog";
import { DealPicker } from "./DealPicker";
import type { FinParams } from "./finParams";
import { GapCard } from "./GapCard";
import { ImpactDialog } from "./ImpactDialog";
import { OptionCard } from "./OptionCard";
import { ScheduleDialog } from "./ScheduleDialog";

type Props = { partyId: string | undefined; initial: FinParams };

type Dialog = { kind: "schedule" | "impact" | "apply"; option: OptionQuote };

export function FinancingWorkspace({ partyId, initial }: Props) {
  const t = useT();
  const [mode, setMode] = useState<FinMode>(initial.mode);
  const [deal, setDeal] = useState<string | undefined>(initial.deal);
  const [edited, setEdited] = useState<string | null>(initial.amount ?? null);
  const [currency, setCurrency] = useState<Currency>(initial.currency ?? "USD");
  const [dialog, setDialog] = useState<Dialog | null>(null);

  const dealReady = mode === "shortfall" || deal !== undefined;
  const gap = useApi(
    (s) => getGap(mode, deal, partyId, s),
    `gap|${mode}|${deal}|${partyId}`,
    dealReady,
  );

  const typed = useDebounced(edited);
  const amountOk = typed !== null && isValidAmount(typed);
  const matchEnabled =
    dealReady &&
    gap.data !== undefined &&
    (typed === null ? !gap.data.no_financing_needed : amountOk);
  const match = useApi(
    (s) =>
      matchOptions(
        {
          mode,
          deal_id: deal,
          party_id: partyId,
          amount: amountOk ? typed : undefined,
        },
        s,
      ),
    `match|${mode}|${deal}|${partyId}|${typed ?? ""}`,
    matchEnabled,
  );
  const apps = useApi((s) => listApplications(partyId, s), `apps|${partyId}`);

  function switchMode(next: FinMode) {
    setMode(next);
    setEdited(null);
  }

  function closeDialog(changed: boolean) {
    setDialog(null);
    if (changed) {
      setEdited(null);
      gap.reload();
      match.reload();
      apps.reload();
    }
  }

  const m = match.data;
  const shown = matchEnabled ? m : undefined;
  const amountValue = edited ?? gap.data?.amount[gap.data.currency] ?? "";
  const busy = matchEnabled && match.loading;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-ink">{t("fin.title")}</h1>
        <SimulatedBadge />
      </div>
      <p className="text-muted">{t("fin.intro")}</p>

      <div className="flex flex-wrap items-end gap-4">
        <SegmentedControl<FinMode>
          legend={t("fin.mode.label")}
          value={mode}
          onChange={switchMode}
          options={[
            { value: "shortfall", label: t("fin.mode.shortfall") },
            { value: "order", label: t("fin.mode.order") },
          ]}
        />
        <CurrencyToggle value={currency} onChange={setCurrency} />
      </div>

      {mode === "order" ? (
        <DealPicker
          value={deal}
          onChange={(v) => {
            setDeal(v || undefined);
            setEdited(null);
          }}
        />
      ) : null}

      {!dealReady ? (
        <EmptyState title={t("fin.deal.pick")} />
      ) : gap.error ? (
        <QueryError error={gap.error} onRetry={gap.reload} />
      ) : !gap.data ? (
        <div aria-busy="true" className="space-y-3">
          <Skeleton className="h-40" />
          <Skeleton className="h-72" />
        </div>
      ) : (
        <>
          <GapCard gap={gap.data} currency={currency} />
          <AmountControls
            value={amountValue}
            gap={gap.data}
            onChange={setEdited}
            onUseSuggested={() => setEdited(null)}
          />

          <section
            aria-labelledby="fin-options-h"
            aria-busy={busy}
            className="space-y-4"
          >
            <h2 id="fin-options-h" className="text-lg font-bold text-ink">
              {t("fin.options.title")}
            </h2>
            <p role="status" className="sr-only">
              {busy ? t("common.updating") : ""}
            </p>
            {match.error && matchEnabled ? (
              <QueryError error={match.error} onRetry={match.reload} />
            ) : !matchEnabled ? (
              <EmptyState
                title={
                  typed !== null && !amountOk
                    ? t("fin.amount.invalid")
                    : t("fin.noneNeeded")
                }
              />
            ) : !shown ? (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <Skeleton className="h-96" />
                <Skeleton className="h-96" />
                <Skeleton className="h-96" />
              </div>
            ) : (
              <ul
                className={`grid gap-4 md:grid-cols-2 xl:grid-cols-3 ${busy ? "opacity-60" : ""}`}
              >
                {shown.options.map((o) => (
                  <OptionCard
                    key={o.code}
                    option={o}
                    pick={shown.top_pick}
                    currency={currency}
                    onSchedule={(opt) =>
                      setDialog({ kind: "schedule", option: opt })
                    }
                    onImpact={(opt) =>
                      setDialog({ kind: "impact", option: opt })
                    }
                    onApply={(opt) => setDialog({ kind: "apply", option: opt })}
                  />
                ))}
              </ul>
            )}
          </section>

          {dialog && shown ? (
            dialog.kind === "schedule" ? (
              <ScheduleDialog
                option={dialog.option}
                amount={shown.amount[shown.currency]}
                dealId={shown.deal.reference}
                partyId={partyId}
                currency={currency}
                onClose={() => setDialog(null)}
              />
            ) : dialog.kind === "impact" ? (
              <ImpactDialog
                option={dialog.option}
                amount={shown.amount[shown.currency]}
                mode={mode}
                dealId={shown.deal.reference}
                partyId={partyId}
                onClose={() => setDialog(null)}
              />
            ) : (
              <ApplyDialog
                option={dialog.option}
                amount={shown.amount[shown.currency]}
                mode={mode}
                dealId={shown.deal.reference}
                partyId={partyId}
                currency={currency}
                onClose={closeDialog}
              />
            )
          ) : null}
        </>
      )}

      <ApplicationsList
        applications={apps.data?.applications}
        error={apps.error}
        onRetry={apps.reload}
        currency={currency}
      />
    </div>
  );
}
