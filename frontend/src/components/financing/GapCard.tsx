"use client";

import { Money } from "@/components/analysis/Money";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useLang, useT } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";
import type { Gap } from "@/lib/api/financing";
import { formatDate } from "@/lib/format";

import { ExplanationList } from "./ExplanationList";

type Props = { gap: Gap; currency: Currency };

export function GapCard({ gap, currency }: Props) {
  const t = useT();
  const { lang } = useLang();
  if (gap.no_financing_needed) {
    return (
      <EmptyState
        title={t("fin.noneNeeded")}
        body={t(
          gap.mode === "order" ? "fin.noneNeededOrder" : "fin.noneNeededBody",
        )}
      />
    );
  }
  const rows: [string, React.ReactNode][] = [
    [
      t("fin.gap.amount"),
      <Money key="a" amounts={gap.amount} currency={currency} />,
    ],
    [t("fin.gap.neededBy"), formatDate(gap.needed_by, lang)],
    [t("fin.gap.forDays"), t("fin.days", { n: gap.needed_for_days })],
  ];
  if (gap.landed_cost) {
    rows.push([
      t("fin.gap.landed"),
      <Money key="l" amounts={gap.landed_cost} currency={currency} />,
    ]);
  }
  if (gap.available_cash) {
    rows.push([
      t("fin.gap.cash"),
      <Money key="c" amounts={gap.available_cash} currency={currency} />,
    ]);
  }
  if (gap.recover_on) {
    rows.push([
      t(gap.mode === "order" ? "fin.gap.release" : "fin.gap.recovers"),
      formatDate(gap.recover_on, lang),
    ]);
  }
  return (
    <Card as="section" labelledBy="fin-gap-h" className="space-y-4">
      <h2 id="fin-gap-h" className="text-lg font-bold text-ink">
        {t("fin.gap.title")}
      </h2>
      <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt className="text-muted">{k}</dt>
            <dd className="text-base font-semibold text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      <div>
        <h3 className="mb-1 text-sm font-semibold text-ink">
          {t("fin.gap.why")}
        </h3>
        <ExplanationList items={gap.explanations} />
      </div>
      {gap.facts.length > 0 ? (
        <details className="text-sm text-muted">
          <summary className="cursor-pointer font-medium focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
            {t("fin.gap.facts")}
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {gap.facts.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </Card>
  );
}
