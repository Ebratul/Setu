"use client";

import Link from "next/link";
import { Fragment, useState } from "react";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getRiskOverview, getRiskPolicy, type RiskEvent, type RiskOverview } from "@/lib/api/risk";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { PolicyTable } from "./PolicyTable";
import { fmtInt, pick } from "./riskText";
import { RuleTrace } from "./RuleTrace";
import { TierBadge } from "./TierBadge";

const th = "px-3 py-2 text-left font-semibold";
const td = "px-3 py-2 align-top";

export function RiskAdminPage() {
  const t = useT();
  const overview = useApi((s) => getRiskOverview(s), "risk-overview");
  const policy = useApi((s) => getRiskPolicy(s), "risk-policy");
  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("risk.admin.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="text-muted">{t("risk.admin.intro")}</p>
        <Link
          href="/demo/risk-playground"
          className="inline-block font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        >
          {t("risk.admin.playground")}
        </Link>
      </header>

      {overview.error ? (
        <QueryError error={overview.error} onRetry={overview.reload} />
      ) : !overview.data ? (
        <Skeleton className="h-64" />
      ) : (
        <Overview data={overview.data} />
      )}

      <section aria-labelledby="risk-policy-h" className="space-y-3">
        <h2 id="risk-policy-h" className="text-lg font-bold text-ink">
          {t("risk.policy.title")}
        </h2>
        <p className="text-sm text-muted">{t("risk.policy.intro")}</p>
        {policy.error ? (
          <QueryError error={policy.error} onRetry={policy.reload} />
        ) : policy.data ? (
          <PolicyTable policy={policy.data} />
        ) : (
          <Skeleton className="h-48" />
        )}
      </section>
    </div>
  );
}

function Overview({ data }: { data: RiskOverview }) {
  const t = useT();
  const c = data.counters;
  const tiles: { label: string; value: number; icon: string; cls: string; id: string }[] = [
    { id: "auto", label: t("risk.admin.autoReleased"), value: c.auto_released, icon: "✓", cls: "text-success" },
    { id: "one-tap", label: t("risk.admin.oneTap"), value: c.one_tap, icon: "▲", cls: "text-warning" },
    { id: "otp", label: t("risk.admin.otp"), value: c.otp_required, icon: "⚠", cls: "text-danger" },
    { id: "blocked", label: t("risk.admin.blocked"), value: c.blocked, icon: "⛔", cls: "text-danger" },
  ];
  return (
    <>
      <ul className="grid grid-cols-2 gap-4 lg:grid-cols-4" data-testid="risk-counters">
        {tiles.map((x) => (
          <li key={x.id}>
            <Card className="h-full">
              <p className="text-sm text-muted">{x.label}</p>
              <p className={`text-3xl font-bold tabular-nums ${x.cls}`} data-testid={`counter-${x.id}`}>
                <span aria-hidden="true">{x.icon} </span>
                {x.value}
              </p>
            </Card>
          </li>
        ))}
      </ul>
      <DecisionsChart series={data.series} />
      <section aria-labelledby="risk-latest-h" className="space-y-3">
        <h2 id="risk-latest-h" className="text-lg font-bold text-ink">
          {t("risk.admin.latest")}
        </h2>
        <LatestBlocked rows={data.latest_blocked} />
      </section>
      <section aria-labelledby="risk-recent-h" className="space-y-3">
        <h2 id="risk-recent-h" className="text-lg font-bold text-ink">
          {t("risk.admin.recent")}
        </h2>
        <RecentTable rows={data.recent} />
      </section>
    </>
  );
}

const SERIES = [
  { key: "auto", label: "risk.admin.autoReleased", fill: "fill-success", bg: "bg-success" },
  { key: "one_tap", label: "risk.admin.oneTap", fill: "fill-info", bg: "bg-info" },
  { key: "otp", label: "risk.admin.otp", fill: "fill-warning", bg: "bg-warning" },
  { key: "blocked", label: "risk.admin.blocked", fill: "fill-danger", bg: "bg-danger" },
] as const;

function DecisionsChart({ series }: { series: RiskOverview["series"] }) {
  const t = useT();
  const { lang } = useLang();
  const [table, setTable] = useState(false);
  const total = (p: RiskOverview["series"][number]) => p.auto + p.one_tap + p.otp + p.blocked;
  const max = Math.max(1, ...series.map(total));
  const W = 40;
  const H = 140;
  return (
    <Card as="section" labelledBy="risk-chart-h" className="space-y-3">
      <h2 id="risk-chart-h" className="text-lg font-bold text-ink">
        {t("risk.admin.chart")}
      </h2>
      {series.length === 0 ? (
        <p className="text-sm text-muted">{t("risk.admin.noSeries")}</p>
      ) : (
        <>
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink" aria-label={t("risk.admin.chart")}>
            {SERIES.map((s) => (
              <li key={s.key} className="flex items-center gap-1">
                <span aria-hidden="true" className={`inline-block size-3 rounded-sm ${s.bg}`} />
                {t(s.label)}
              </li>
            ))}
          </ul>
          <div className="overflow-x-auto">
            <svg
              role="img"
              aria-label={t("risk.admin.chart")}
              viewBox={`0 0 ${series.length * W} ${H + 18}`}
              style={{ minWidth: series.length * 28 }}
              className="h-48 w-full"
              data-testid="risk-chart"
            >
              {series.map((p, i) => {
                let y = H;
                return (
                  <g key={p.day}>
                    <title>
                      {p.day}: {SERIES.map((s) => `${t(s.label)} ${p[s.key]}`).join(", ")}
                    </title>
                    {SERIES.map((s) => {
                      const h = (p[s.key] / max) * H;
                      y -= h;
                      return h > 0 ? (
                        <rect key={s.key} x={i * W + 6} y={y} width={W - 12} height={h} className={s.fill} />
                      ) : null;
                    })}
                    <text x={i * W + W / 2} y={H + 13} textAnchor="middle" className="fill-muted" fontSize="9">
                      {p.day.slice(5)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
          <button
            type="button"
            aria-expanded={table}
            onClick={() => setTable((v) => !v)}
            className="rounded-md text-sm font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            {t(table ? "risk.admin.chartTableHide" : "risk.admin.chartTable")}
          </button>
          {table ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-96 text-sm" data-testid="risk-series-table">
                <caption className="sr-only">{t("risk.admin.chart")}</caption>
                <thead>
                  <tr className="border-b border-line text-muted">
                    <th scope="col" className={th}>{t("risk.admin.day")}</th>
                    {SERIES.map((s) => (
                      <th key={s.key} scope="col" className={`${th} text-right`}>{t(s.label)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {series.map((p) => (
                    <tr key={p.day} className="border-b border-line last:border-0">
                      <th scope="row" className={`${td} text-left font-normal`}>{formatDate(p.day, lang)}</th>
                      {SERIES.map((s) => (
                        <td key={s.key} className={`${td} text-right tabular-nums`}>
                          {fmtInt(String(p[s.key]), lang)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}

function reasonLabel(e: RiskEvent, code: string, lang: "en" | "bn" | "zh") {
  const item = e.trace.find((i) => i.code === code);
  return item ? pick(lang, item.label_en, item.label_bn) : code;
}

function LatestBlocked({ rows }: { rows: RiskEvent[] }) {
  const t = useT();
  const { lang } = useLang();
  if (rows.length === 0) return <EmptyState title={t("risk.admin.noBlocked")} />;
  return (
    <ul className="space-y-2" data-testid="latest-blocked">
      {rows.map((e) => (
        <li key={e.id}>
          <Card className="border border-danger">
            <div className="flex flex-wrap items-center gap-2">
              <TierBadge tier={e.tier} decision="BLOCK" />
              <span className="font-semibold text-ink">{e.deal_ref ?? "—"}</span>
              <span className="text-sm text-muted">
                {e.action} · {formatDate(e.ts.slice(0, 10), lang)}
              </span>
            </div>
            <p className="mt-1 text-sm text-ink">
              {e.reason_codes.map((c) => reasonLabel(e, c, lang)).join(", ")}
            </p>
          </Card>
        </li>
      ))}
    </ul>
  );
}

function RecentTable({ rows }: { rows: RiskEvent[] }) {
  const t = useT();
  const { lang } = useLang();
  const [open, setOpen] = useState<string | null>(null);
  if (rows.length === 0) return <EmptyState title={t("risk.admin.noRecent")} />;
  return (
    <Card>
      <div className="overflow-x-auto">
        <table className="w-full min-w-208 text-sm" data-testid="risk-recent">
          <caption className="sr-only">{t("risk.admin.recent")}</caption>
          <thead>
            <tr className="border-b border-line text-muted">
              <th scope="col" className={th}>{t("risk.admin.when")}</th>
              <th scope="col" className={th}>{t("risk.admin.deal")}</th>
              <th scope="col" className={th}>{t("risk.admin.action")}</th>
              <th scope="col" className={th}>{t("risk.admin.tier")}</th>
              <th scope="col" className={th}>{t("risk.admin.decision")}</th>
              <th scope="col" className={th}>{t("risk.admin.reasons")}</th>
              <th scope="col" className={th}>{t("risk.admin.origin")}</th>
              <th scope="col" className={th}>
                <span className="sr-only">{t("risk.trace.title")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => {
              const expanded = open === e.id;
              return (
                <Fragment key={e.id}>
                  <tr className="border-b border-line" data-testid="risk-row">
                    <td className={td}>{formatDate(e.ts.slice(0, 10), lang)}</td>
                    <td className={td}>{e.deal_ref ?? "—"}</td>
                    <td className={td}>{e.action}</td>
                    <td className={td}>
                      <TierBadge tier={e.tier} decision={e.decision} />
                    </td>
                    <td className={td}>{t(`risk.decision.${e.decision}`)}</td>
                    <td className={td}>{e.reason_codes.map((c) => reasonLabel(e, c, lang)).join(", ") || "—"}</td>
                    <td className={td}>{e.origin}</td>
                    <td className={td}>
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-controls={`trace-${e.id}`}
                        onClick={() => setOpen(expanded ? null : e.id)}
                        className="rounded-md font-semibold whitespace-nowrap text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                      >
                        {t(expanded ? "risk.admin.collapse" : "risk.admin.expand")}
                      </button>
                    </td>
                  </tr>
                  {expanded ? (
                    <tr id={`trace-${e.id}`} className="border-b border-line bg-surface-alt">
                      <td colSpan={8} className="p-3">
                        <RuleTrace trace={e.trace} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
