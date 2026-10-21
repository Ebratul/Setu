"use client";

import { Card } from "@/components/ui/Card";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import type { DealCurrency, EscrowCardData, Milestone } from "@/lib/api/deals";
import { formatMoney } from "@/lib/format";

type Props = {
  escrow: EscrowCardData;
  settlementCurrency: DealCurrency | null;
  milestones: Milestone[];
};

/** Visual share only (bar widths); every amount shown is the server's string. */
function share(part: string, whole: string): number {
  const w = Number(whole);
  return w > 0 ? Math.max(0, Math.min(100, (Number(part) / w) * 100)) : 0;
}

export function EscrowPanel({ escrow, settlementCurrency, milestones }: Props) {
  const t = useT();
  const { lang } = useLang();
  const c = escrow.currency;
  const total = escrow.funded;
  const rows: { key: string; value: string; cls: string; label: string }[] = [
    { key: "released", value: escrow.released, cls: "bg-success", label: t("esc.released") },
    { key: "refunded", value: escrow.refunded, cls: "bg-muted", label: t("esc.refunded") },
    { key: "balance", value: escrow.balance, cls: "bg-brand-600", label: t("esc.balance") },
  ];
  const fx = [...milestones]
    .reverse()
    .find((m) => m.settlement?.fx_rate)?.settlement;

  return (
    <Card as="section" labelledBy="escrow-h" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="escrow-h" className="text-lg font-bold text-ink">
          {t("esc.title")}
        </h2>
        <SimulatedBadge />
      </div>
      <p className="text-sm text-muted">
        {t("esc.status")}: <strong className="text-ink">{escrow.status}</strong>
        {" · "}
        {escrow.partner}
      </p>

      <div>
        <div
          role="img"
          aria-label={t("esc.barLabel", {
            released: formatMoney(escrow.released, c, lang),
            balance: formatMoney(escrow.balance, c, lang),
            funded: formatMoney(escrow.funded, c, lang),
          })}
          className="flex h-4 w-full overflow-hidden rounded-full bg-line"
        >
          {rows.map((r) => (
            <div
              key={r.key}
              className={r.cls}
              style={{ width: `${share(r.value, total)}%` }}
            />
          ))}
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink">
          {rows.map((r) => (
            <li key={r.key} className="flex items-center gap-1">
              <span aria-hidden="true" className={`inline-block h-2.5 w-2.5 rounded-sm ${r.cls}`} />
              {r.label}
            </li>
          ))}
        </ul>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4" data-testid="escrow-card">
        {(
          [
            ["esc.funded", escrow.funded, "funded"],
            ["esc.released", escrow.released, "released"],
            ["esc.refunded", escrow.refunded, "refunded"],
            ["esc.balance", escrow.balance, "balance"],
          ] as const
        ).map(([k, v, id]) => (
          <div key={k}>
            <dt className="text-muted">{t(k)}</dt>
            <dd
              data-testid={`escrow-${id}`}
              className="font-bold text-ink tabular-nums"
              aria-label={`${formatMoney(v, c, lang)} ${c}`}
            >
              {formatMoney(v, c, lang)}
            </dd>
          </div>
        ))}
      </dl>

      <p className="text-sm text-ink">
        {t("esc.remaining")}:{" "}
        <strong className="tabular-nums">
          {formatMoney(escrow.remaining_to_fund, c, lang)}
        </strong>
      </p>
      {settlementCurrency && settlementCurrency !== c ? (
        <p className="text-sm text-ink" data-testid="escrow-settlement"
          data-demo="settlement">
          {t("esc.settlement", { currency: settlementCurrency })}
          {fx?.fx_rate
            ? ` · ${t("esc.fx", { rate: fx.fx_rate, from: c, to: settlementCurrency })}`
            : ""}
        </p>
      ) : null}
      {escrow.advance_over_20k ? (
        <p className="rounded-xl border border-warning bg-warning-soft p-2 text-xs text-ink">
          <span aria-hidden="true">▲ </span>
          {t("esc.over20k")}
        </p>
      ) : null}
      {!escrow.invariant_ok ? (
        <p role="alert" className="text-sm font-semibold text-danger">
          ✕ {t("esc.invariantBad")}
        </p>
      ) : null}
    </Card>
  );
}
