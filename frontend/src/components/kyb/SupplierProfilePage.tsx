"use client";

import Link from "next/link";
import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import {
  getSupplier,
  type AccountSummary,
  type KybResult,
  type SupplierProfile,
} from "@/lib/api/kyb";
import { formatDate, formatDecimal, formatMoney, formatPct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { KybBadge } from "./KybBadge";
import { InfoTip } from "@/components/docs/InfoTip";
import { KybChecks } from "./KybChecks";
import { RerunButton } from "./RerunButton";
import { ScoreBar } from "./ScoreBar";
import { ScoreTrendChart } from "./ScoreTrendChart";

const th = "py-2 pr-3 text-left font-medium text-muted";
const td = "py-2 pr-3 text-ink";

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card as="section" labelledBy={id} className="space-y-3">
      <h2 id={id} className="flex items-center gap-2 text-lg font-bold text-ink">
        {title}
        {id === "status-h" ? <InfoTip topic="kyb" doc="buyer/suppliers-kyb#what-it-is" /> : null}
      </h2>
      {children}
    </Card>
  );
}

function Accounts({ accounts }: { accounts: AccountSummary[] }) {
  const t = useT();
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-120 text-sm">
        <caption className="sr-only">{t("sup.accountsCaption")}</caption>
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className={th}>{t("sup.acc.number")}</th>
            <th scope="col" className={th}>{t("sup.acc.holder")}</th>
            <th scope="col" className={th}>{t("sup.acc.type")}</th>
            <th scope="col" className={th}>{t("sup.acc.age")}</th>
            <th scope="col" className={th}>{t("sup.acc.status")}</th>
            <th scope="col" className={th}>{t("sup.acc.currency")}</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((a) => (
            <tr key={a.account_id} data-testid="account-row" className="border-b border-line last:border-0">
              <th scope="row" className={`${td} text-left font-semibold`}>
                <span className="break-all">{a.masked_number}</span>
                <span className="block text-xs font-normal text-muted">
                  {a.bank_name} · {a.bank_country}
                </span>
              </th>
              <td className={td}>{a.holder_name}</td>
              <td className={td}>{t(`sup.accType.${a.account_type}`)}</td>
              <td className={td}>{t("sup.days", { n: a.age_days })}</td>
              <td className={td}>
                <span className="font-semibold">{t(`sup.accStatus.${a.status}`)}</span>
              </td>
              <td className={td}>{a.currency}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PendingSection({ kyb }: { kyb: KybResult }) {
  const t = useT();
  const { lang } = useLang();
  if (kyb.pending_accounts.length === 0) return null;
  return (
    <section
      role="region"
      aria-labelledby="pending-h"
      data-testid="pending-section"
      className="space-y-3 rounded-card border-2 border-warning bg-warning-soft p-5"
    >
      <h2 id="pending-h" className="flex items-center gap-2 text-lg font-bold text-warning">
        <span aria-hidden="true">▲</span>
        {t("sup.pendingTitle")}
      </h2>
      <p className="text-sm text-ink">{t("sup.pendingBody")}</p>
      {kyb.pending_accounts.map((p) => (
        <div key={p.account.account_id} className="space-y-2 rounded-xl bg-surface p-3">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink">
            {t("sup.pendingAccount", {
              number: p.account.masked_number,
              status: t(`kyb.${p.status}`),
            })}
            <KybBadge status={p.status} />
          </p>
          <p className="text-sm text-ink">
            {lang === "bn" ? p.explanation_bn : p.explanation_en}
          </p>
          <KybChecks
            checks={p.checks.filter((c) => c.status !== "PASS")}
            label={t("sup.pendingTitle")}
          />
        </div>
      ))}
    </section>
  );
}

function Loaded({
  profile,
  reload,
}: {
  profile: SupplierProfile;
  reload: () => void;
}) {
  const t = useT();
  const { lang } = useLang();
  const me = useApi(getMe, "me-role");
  const [fresh, setFresh] = useState<KybResult | null>(null);
  const kyb = fresh ?? profile.kyb;
  const co = profile.company;
  const canRun = me.data?.role === "BUYER" || me.data?.role === "ADMIN";
  const readOnly = me.data?.role === "JUDGE";
  const rows: [string, string][] = [
    [t("sup.legalName"), co.legal_name],
    [t("sup.licenseName"), co.license_name ?? "—"],
    [t("sup.licenseNo"), co.license_no ?? "—"],
    [t("sup.city"), co.city],
    [t("sup.country"), co.country],
    [t("sup.firstSeen"), formatDate(co.first_seen_on, lang)],
  ];
  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/app/suppliers"
          className="rounded text-sm font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          ← {t("sup.back")}
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold break-words text-ink">{co.legal_name}</h1>
          <span data-demo="kyb-badge" className="inline-flex">
            <KybBadge status={kyb.status} />
          </span>
          <SimulatedBadge />
        </div>
      </div>

      <PendingSection kyb={kyb} />

      <Section id="status-h" title={t("sup.checks")}>
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <p className="text-xs text-muted">{t("sup.score")}</p>
            <ScoreBar score={kyb.score} />
          </div>
          <p className="text-xs text-muted">
            {formatDate(kyb.checked_at.slice(0, 10), lang)}
            {profile.kyb_source === "live" ? ` · ${t("sup.liveNote")}` : ""}
          </p>
          <div className="ms-auto">
            {canRun ? (
              <RerunButton
                supplierId={profile.supplier_id}
                onDone={(r) => {
                  setFresh(r);
                  reload();
                }}
              />
            ) : readOnly ? (
              <p className="text-sm text-muted">{t("sup.readOnly")}</p>
            ) : null}
          </div>
        </div>
        <p className="text-sm text-ink">
          {lang === "bn" ? kyb.explanation_bn : kyb.explanation_en}
        </p>
        <KybChecks checks={kyb.checks} label={t("sup.checks")} />
      </Section>

      <Section id="company-h" title={t("sup.company")}>
        <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt className="text-muted">{k}</dt>
              <dd className="font-semibold break-words text-ink">{v}</dd>
            </div>
          ))}
          <div>
            <dt className="text-muted">{t("sup.onTimeRate")}</dt>
            <dd className="font-semibold text-ink">
              {profile.on_time_rate_pct ? formatPct(profile.on_time_rate_pct, lang) : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted">{t("sup.disputeRate")}</dt>
            <dd className="font-semibold text-ink">
              {profile.dispute_rate_pct ? formatPct(profile.dispute_rate_pct, lang) : "—"}
            </dd>
          </div>
        </dl>
      </Section>

      <Section id="accounts-h" title={t("sup.accounts")}>
        <Accounts accounts={profile.accounts} />
      </Section>

      <Section id="deals-h" title={t("sup.deals")}>
        {profile.deals.length === 0 ? (
          <p className="text-sm text-muted">{t("sup.dealsEmpty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-120 text-sm">
              <caption className="sr-only">{t("sup.dealsCaption")}</caption>
              <thead>
                <tr className="border-b border-line">
                  <th scope="col" className={th}>{t("sup.deal.ref")}</th>
                  <th scope="col" className={th}>{t("sup.deal.status")}</th>
                  <th scope="col" className={th}>{t("sup.deal.value")}</th>
                  <th scope="col" className={th}>{t("sup.deal.opened")}</th>
                  <th scope="col" className={th}>{t("sup.deal.onTime")}</th>
                </tr>
              </thead>
              <tbody>
                {profile.deals.map((d) => (
                  <tr key={d.deal_id} className="border-b border-line last:border-0">
                    <th scope="row" className={`${td} text-left font-semibold`}>
                      <Link
                        href={`/app/deals/${d.reference}`}
                        className="rounded text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                      >
                        {d.reference}
                      </Link>
                      <span className="block text-xs font-normal text-muted">{d.title}</span>
                    </th>
                    <td className={td}>
                      {t(`status.${d.status}`) === `status.${d.status}` ? d.status : t(`status.${d.status}`)}
                    </td>
                    <td className={td}>
                      {formatMoney(d.goods_value, d.currency as "USD" | "BDT" | "CNY", lang)}
                    </td>
                    <td className={td}>{formatDate(d.opened_on, lang)}</td>
                    <td className={td}>
                      {d.on_time === null ? "—" : d.on_time ? t("sup.yes") : t("sup.no")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section id="trend-h" title={t("sup.trend")}>
        <ScoreTrendChart points={profile.score_trend} />
      </Section>

      {profile.history.length > 0 ? (
        <Section id="hist-h" title={t("sup.history")}>
          <table className="w-full text-sm">
            <caption className="sr-only">{t("sup.historyCaption")}</caption>
            <tbody>
              {profile.history.map((h) => (
                <tr key={h.id} className="border-b border-line last:border-0">
                  <th scope="row" className={`${td} text-left font-medium`}>
                    {formatDate(h.checked_at.slice(0, 10), lang)}
                  </th>
                  <td className={td}><KybBadge status={h.status} /></td>
                  <td className={`${td} tabular-nums`}>{formatDecimal(String(h.score), lang, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}
    </div>
  );
}

export function SupplierProfilePage({ id }: { id: string }) {
  const { data, error, reload } = useApi((s) => getSupplier(id, s), `supplier|${id}`);
  if (error) return <QueryError error={error} onRetry={reload} />;
  if (!data) return <Skeleton className="h-64" />;
  return <Loaded profile={data} reload={reload} />;
}
