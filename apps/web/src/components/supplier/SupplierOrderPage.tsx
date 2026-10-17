"use client";

import Link from "next/link";
import { useState } from "react";

import { StatusBadge } from "@/components/analysis/StatusBadge";
import { ConfirmScheduleDialog } from "@/components/deals/DealActions";
import { MilestoneStepper } from "@/components/deals/MilestoneStepper";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getDeal, getLedger, type DealDetail } from "@/lib/api/deals";
import { formatDate, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { Bi } from "./Bi";
import { SupplierDocuments } from "./SupplierDocuments";

export function SupplierOrderPage({ reference }: { reference: string }) {
  const t = useT();
  const deal = useApi((s) => getDeal(reference, s), `sp-deal|${reference}`);
  if (deal.error) return <QueryError error={deal.error} onRetry={deal.reload} />;
  if (!deal.data) return <Skeleton className="h-64" />;
  return <Body deal={deal.data} reload={deal.reload} back={t("sp.back")} />;
}

function Body({ deal, reload, back }: { deal: DealDetail; reload: () => void; back: string }) {
  const t = useT();
  const { lang } = useLang();
  const [confirming, setConfirming] = useState(false);
  const sig = `${deal.status}|${deal.escrow.released}`;
  const ledger = useApi((s) => getLedger(deal.id, s), `sp-ledger|${deal.id}|${sig}`);
  const c = deal.escrow.currency;
  const flag = deal.can.can_confirm;
  const payments = (ledger.data?.rows ?? []).filter(
    (r) => r.kind === "RELEASE" && r.direction === "CREDIT",
  );
  const rows: [string, string][] = [
    [t("sp.orderValue"), formatMoney(deal.goods_value, deal.currency, lang)],
    [t("orders.quantity"), `${deal.quantity} ${deal.unit}`],
    [t("dd.unitPrice"), formatMoney(deal.unit_price, deal.currency, lang)],
    [t("orders.incoterm"), deal.incoterm],
    [t("dd.route"), `${deal.port_of_loading} → ${deal.port_of_discharge}`],
    [t("orders.opened"), formatDate(deal.opened_on, lang)],
  ];

  return (
    <div className="space-y-6">
      <Link
        href="/supplier"
        className="text-sm font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
      >
        ← {back}
      </Link>
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{deal.reference}</h1>
          <StatusBadge status={deal.status} />
        </div>
        <p className="text-muted">{deal.title}</p>
        <p className="text-sm text-ink">{t("sp.buyer", { name: deal.buyer_name })}</p>
      </header>

      <Card
        as="section"
        labelledBy="sp-escrow-h"
        className="space-y-1 border-2 border-success bg-success-soft"
      >
        <h2 id="sp-escrow-h" className="sr-only">
          {t("sp.escrowHeading")}
        </h2>
        <p data-testid="funds-secured" className="text-lg font-bold text-ink">
          <span aria-hidden="true">✓ </span>
          <Bi k="sp.fundsSecured" vars={{ amount: formatMoney(deal.escrow.balance, c, lang) }} />
        </p>
        <p className="text-xs text-muted">{t("sp.escrowNote")}</p>
      </Card>

      <section aria-labelledby="sp-ms-h" className="space-y-3">
        <h2 id="sp-ms-h" className="text-lg font-bold text-ink">
          <Bi k="sp.milestones" />
        </h2>
        {deal.milestones.length === 0 ? (
          <Card>
            <p className="text-sm text-muted">{t("ms.none")}</p>
          </Card>
        ) : (
          <MilestoneStepper milestones={deal.milestones} currency={deal.currency} />
        )}
        {deal.confirmations.length > 0 ? (
          <ul className="space-y-1 text-sm">
            {deal.confirmations.map((x) => (
              <li key={x.party_role} data-testid="confirmation" className="flex gap-2">
                <span aria-hidden="true">{x.confirmed ? "✓" : "○"}</span>
                {t(`role.${x.party_role}`)}: {x.confirmed ? t("dd.confirmed") : t("dd.notConfirmed")}
              </li>
            ))}
          </ul>
        ) : null}
        {deal.milestones.length > 0 ? (
          <div>
            <Button
              disabled={!flag.allowed}
              aria-describedby={flag.allowed ? undefined : "sp-confirm-why"}
              onClick={() => setConfirming(true)}
              data-testid="action-confirm"
            >
              {t("act2.confirm")}
            </Button>
            {!flag.allowed && flag.reason ? (
              <p id="sp-confirm-why" className="mt-1 text-xs text-muted">
                {flag.reason}
              </p>
            ) : null}
          </div>
        ) : null}
      </section>

      {deal.status !== "CANCELLED" ? <SupplierDocuments dealId={deal.id} onChanged={reload} /> : null}

      <Card as="section" labelledBy="sp-pay-h" className="space-y-3">
        <h2 id="sp-pay-h" className="text-lg font-bold text-ink">
          <Bi k="sp.payments" />
        </h2>
        {payments.length === 0 ? (
          <p className="text-sm text-muted">{t("sp.noPayments")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-96 text-sm" data-testid="payments">
              <caption className="sr-only">{t("sp.payments")}</caption>
              <thead>
                <tr className="border-b border-line text-left text-muted">
                  <th scope="col" className="py-2 pr-3 font-medium">{t("led.milestone")}</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">{t("led.amount")}</th>
                  <th scope="col" className="py-2 pr-3 font-medium">{t("led.fx")}</th>
                  <th scope="col" className="py-2 font-medium">{t("led.posted")}</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((r) => (
                  <tr key={r.id} className="border-b border-line last:border-0">
                    <td className="py-2 pr-3">{r.milestone_seq ?? "—"}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{formatMoney(r.amount, r.currency, lang)}</td>
                    <td className="py-2 pr-3 text-xs tabular-nums">
                      {r.fx_rate && r.counter_amount && r.counter_currency
                        ? t("led.fxDetail", {
                            rate: r.fx_rate,
                            amount: formatMoney(r.counter_amount, r.counter_currency, lang),
                          })
                        : "—"}
                    </td>
                    <td className="py-2 text-xs">
                      {new Intl.DateTimeFormat(lang === "zh" ? "zh-CN" : "en-US", { dateStyle: "medium" }).format(new Date(r.posted_at))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card as="section" labelledBy="sp-det-h">
        <h2 id="sp-det-h" className="mb-3 text-lg font-bold text-ink">
          <Bi k="sp.details" />
        </h2>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt className="text-muted">{k}</dt>
              <dd className="font-semibold break-words text-ink">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>

      {confirming ? (
        <ConfirmScheduleDialog deal={deal} onClose={() => setConfirming(false)} onDone={reload} />
      ) : null}
    </div>
  );
}
