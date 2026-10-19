"use client";

import Link from "next/link";
import { useState } from "react";

import { StatusBadge } from "@/components/analysis/StatusBadge";
import { DocumentsTab } from "@/components/documents/DocumentsTab";
import { DealKybPanel } from "@/components/kyb/DealKybPanel";
import { KybBadge } from "@/components/kyb/KybBadge";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Tabs } from "@/components/ui/Tabs";
import { useLang, useT } from "@/i18n";
import {
  getActivity,
  getDeal,
  getLedger,
  type DealDetail,
  type Milestone,
} from "@/lib/api/deals";
import type { KybBadgeStatus } from "@/lib/api/kyb";
import { formatDate, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { ActivityList } from "./ActivityList";
import { ApprovalTrail } from "./ApprovalTrail";
import { DealActions, ReleaseDialog } from "./DealActions";
import { DevEvidenceControl } from "./DevEvidenceControl";
import { EscrowPanel } from "./EscrowPanel";
import { LenderCheckDemo } from "./LenderCheckDemo";
import { LedgerTable } from "./LedgerTable";
import { MilestoneStepper } from "./MilestoneStepper";

const KYB: KybBadgeStatus[] = ["VERIFIED", "WARNING", "BLOCKED", "PENDING"];
const linkCls =
  "font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function DealDetailPage({ reference }: { reference: string }) {
  const t = useT();
  const deal = useApi((s) => getDeal(reference, s), `deal-detail|${reference}`);
  const [tab, setTab] = useState("overview");
  if (deal.error) return <QueryError error={deal.error} onRetry={deal.reload} />;
  if (!deal.data) return <Skeleton className="h-96" />;
  const d = deal.data;

  return (
    <div className="space-y-6">
      <DealHeader deal={d} />
      <Tabs
        label={t("dd.tabs")}
        selected={tab}
        onSelect={setTab}
        tabs={[
          { id: "overview", label: t("dd.tab.overview") },
          { id: "documents", label: t("dd.tab.documents") },
          { id: "analysis", label: t("dd.tab.analysis") },
          { id: "activity", label: t("dd.tab.activity") },
        ]}
      >
        {tab === "overview" ? <Overview deal={d} reload={deal.reload} /> : null}
        {tab === "documents" ? <DocumentsTab deal={d} onChanged={deal.reload} /> : null}
        {tab === "analysis" ? <AnalysisLinks deal={d} /> : null}
        {tab === "activity" ? <Activity deal={d} /> : null}
      </Tabs>
    </div>
  );
}

function DealHeader({ deal }: { deal: DealDetail }) {
  const t = useT();
  const kyb = (KYB as string[]).includes(deal.kyb.status)
    ? (deal.kyb.status as KybBadgeStatus)
    : "PENDING";
  return (
    <header className="space-y-2">
      <Link href="/app/deals" className={`text-sm ${linkCls}`}>
        ← {t("nav.orders")}
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-ink">{deal.reference}</h1>
        <StatusBadge status={deal.status} />
        <SimulatedBadge />
      </div>
      <p className="text-muted">{deal.title}</p>
      <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
        {t("orders.supplier")}: <strong>{deal.supplier_name}</strong>
        <KybBadge status={kyb} />
      </p>
    </header>
  );
}

function Overview({ deal, reload }: { deal: DealDetail; reload: () => void }) {
  const t = useT();
  const { lang } = useLang();
  const [releasing, setReleasing] = useState<Milestone | null>(null);
  const sig = `${deal.status}|${deal.escrow.balance}|${deal.milestones.map((m) => m.status).join()}`;
  const ledger = useApi((s) => getLedger(deal.id, s), `ledger|${deal.id}|${sig}`);
  const showRelease = deal.viewer_role === "BUYER" || deal.viewer_role === "ADMIN";
  const c = deal.currency;

  const rows: [string, string][] = [
    [t("orders.hs"), deal.hs_code],
    [t("orders.quantity"), `${deal.quantity} ${deal.unit}`],
    [t("dd.unitPrice"), formatMoney(deal.unit_price, c, lang)],
    [t("orders.goodsValue"), formatMoney(deal.goods_value, c, lang)],
    [t("orders.incoterm"), deal.incoterm],
    [t("dd.route"), `${deal.port_of_loading} → ${deal.port_of_discharge}`],
    [t("dd.settlement"), deal.settlement_currency ?? "—"],
    [t("dd.beneficiary"), deal.beneficiary_masked ?? "—"],
    [t("orders.opened"), formatDate(deal.opened_on, lang)],
  ];

  return (
    <div className="space-y-6">
      {deal.status === "DISPUTED" && deal.dispute_reason ? (
        <p role="alert" className="rounded-xl border-2 border-danger bg-danger-soft p-3 text-sm font-semibold text-danger">
          ▲ {t("dd.disputed", { reason: deal.dispute_reason })}
        </p>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          <DealActions deal={deal} onChanged={reload} />
          <section aria-labelledby="ms-h" className="space-y-3">
            <h2 id="ms-h" className="text-lg font-bold text-ink">
              {t("ms.title")}
            </h2>
            {deal.milestones.length === 0 ? (
              <Card>
                <p className="text-sm text-muted">{t("ms.none")}</p>
              </Card>
            ) : (
              <MilestoneStepper
                milestones={deal.milestones}
                currency={c}
                showRelease={showRelease}
                onRelease={setReleasing}
                extra={(m) => <DevEvidenceControl milestone={m} onDone={reload} />}
              />
            )}
          </section>
          <Confirmations deal={deal} />
          {deal.viewer_role !== "SUPPLIER" ? (
            <ApprovalTrail reference={deal.reference} signature={sig} />
          ) : null}
          <LenderCheckDemo deal={deal} />
        </div>
        <div className="space-y-6">
          <EscrowPanel
            escrow={deal.escrow}
            settlementCurrency={deal.settlement_currency}
            milestones={deal.milestones}
          />
          {deal.viewer_role !== "SUPPLIER" ? (
            <DealKybPanel supplierId={deal.supplier_id} />
          ) : null}
          <Card as="section" labelledBy="det-h">
            <h2 id="det-h" className="mb-3 text-lg font-bold text-ink">
              {t("dd.details")}
            </h2>
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              {rows.map(([k, v]) => (
                <div key={k} className="min-w-0">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-semibold break-words text-ink">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>
      </div>
      {ledger.data ? <LedgerTable ledger={ledger.data} /> : ledger.error ? (
        <QueryError error={ledger.error} onRetry={ledger.reload} />
      ) : (
        <Skeleton className="h-32" />
      )}
      {releasing ? (
        <ReleaseDialog
          deal={deal}
          milestone={releasing}
          onClose={() => setReleasing(null)}
          onDone={reload}
        />
      ) : null}
    </div>
  );
}

function Confirmations({ deal }: { deal: DealDetail }) {
  const t = useT();
  if (deal.confirmations.length === 0) return null;
  return (
    <Card as="section" labelledBy="conf-h" className="space-y-2">
      <h2 id="conf-h" className="text-base font-bold text-ink">
        {t("dd.confirmations")}
      </h2>
      <ul className="space-y-1 text-sm">
        {deal.confirmations.map((c) => (
          <li key={c.party_role} data-testid="confirmation" className="flex items-center gap-2">
            <span aria-hidden="true">{c.confirmed ? "✓" : "○"}</span>
            {t(`role.${c.party_role}`)}:{" "}
            {c.confirmed ? t("dd.confirmed") : t("dd.notConfirmed")}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function AnalysisLinks({ deal }: { deal: DealDetail }) {
  const t = useT();
  const ref = encodeURIComponent(deal.reference);
  return (
    <div className="flex flex-wrap gap-3">
      <Link
        href={`/app/orders/${ref}/analysis`}
        className="inline-block rounded-xl bg-brand-700 px-5 py-3 font-semibold text-white hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        {t("orders.viewAnalysis")} →
      </Link>
      <Link
        href={`/app/financing?deal=${ref}&mode=order`}
        className="inline-block rounded-xl border border-brand-700 bg-surface px-5 py-3 font-semibold text-brand-700 hover:bg-brand-50 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        {t("orders.financing")} →
      </Link>
    </div>
  );
}

function Activity({ deal }: { deal: DealDetail }) {
  const act = useApi((s) => getActivity(deal.id, s), `activity|${deal.id}|${deal.status}`);
  if (act.error) return <QueryError error={act.error} onRetry={act.reload} />;
  if (!act.data) return <Skeleton className="h-32" />;
  return <ActivityList activity={act.data} />;
}
