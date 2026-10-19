"use client";

import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getPrivacyOverview } from "@/lib/api/privacy";
import { formatDate } from "@/lib/format";
import { orderedCounts, tokenize, typeMeta } from "@/lib/privacy/segments";
import type { PrivacyOverview, PrivacyRecord } from "@/lib/privacy/types";
import { useApi } from "@/lib/useApi";

import { PrivacyBadge } from "./PrivacyBadge";
import { PrivacyCounter } from "./PrivacyCounter";
import { fmtNum, typeLabel } from "./privacyText";
import { SegmentText } from "./SegmentText";

const focusRing =
  "focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";
const th = "px-3 py-2 text-left font-semibold";
const td = "px-3 py-2 align-top";

export function PrivacyAdminPage() {
  const t = useT();
  const overview = useApi((s) => getPrivacyOverview(s), "privacy-overview");
  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("privacy.admin.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="text-muted">{t("privacy.admin.intro")}</p>
        <PrivacyCounter />
        <Link
          href="/demo/privacy-playground"
          className={`inline-block rounded-md font-semibold text-brand-700 underline ${focusRing}`}
        >
          {t("privacy.admin.playground")}
        </Link>
      </header>
      {overview.error ? (
        <QueryError error={overview.error} onRetry={overview.reload} />
      ) : !overview.data ? (
        <Skeleton className="h-64" />
      ) : (
        <Overview data={overview.data} />
      )}
    </div>
  );
}

function Overview({ data }: { data: PrivacyOverview }) {
  const t = useT();
  const { lang } = useLang();
  const leaked = data.totals.leaked > 0;
  const counts = orderedCounts(data.by_type);
  const total = counts.reduce((a, [, n]) => a + n, 0);
  return (
    <>
      <p className="flex flex-wrap items-center gap-2 text-sm text-ink" data-testid="privacy-config">
        <Badge tone={data.config.enabled ? "success" : "danger"} icon={data.config.enabled ? "✓" : "⚠"}>
          {t(data.config.enabled ? "privacy.admin.configOn" : "privacy.admin.configOff")}
        </Badge>
        <Badge tone={data.config.mask_amounts ? "success" : "warning"} icon={data.config.mask_amounts ? "✓" : "▲"}>
          {t(data.config.mask_amounts ? "privacy.admin.amountsOn" : "privacy.admin.amountsOff")}
        </Badge>
      </p>

      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-3" data-testid="privacy-totals">
        <li>
          <Card className="h-full">
            <p className="text-sm text-muted">{t("privacy.admin.protected")}</p>
            <p className="text-3xl font-bold text-success tabular-nums" data-testid="total-protected">
              <span aria-hidden="true">🛡 </span>
              {fmtNum(data.totals.protected, lang)}
            </p>
          </Card>
        </li>
        <li>
          <Card className={`h-full ${leaked ? "border border-danger" : ""}`}>
            <p className="text-sm text-muted">{t("privacy.admin.leaked")}</p>
            <p
              className={`text-3xl font-bold tabular-nums ${leaked ? "text-danger" : "text-success"}`}
              data-testid="total-leaked"
            >
              <span aria-hidden="true">{leaked ? "⚠ " : "✓ "}</span>
              {fmtNum(data.totals.leaked, lang)}
            </p>
            <p className="text-xs text-muted">{t("privacy.admin.leakedHint")}</p>
          </Card>
        </li>
        <li>
          <Card className="h-full">
            <p className="text-sm text-muted">{t("privacy.admin.calls")}</p>
            <p className="text-3xl font-bold text-ink tabular-nums" data-testid="total-calls">
              {fmtNum(data.totals.calls, lang)}
            </p>
          </Card>
        </li>
      </ul>

      <Card as="section" labelledBy="priv-bytype-h" className="space-y-3">
        <h2 id="priv-bytype-h" className="text-lg font-bold text-ink">
          {t("privacy.admin.byType")}
        </h2>
        {counts.length === 0 ? (
          <p className="text-sm text-muted">{t("privacy.admin.noData")}</p>
        ) : (
          <ul className="space-y-2" data-testid="by-type">
            {counts.map(([type, n]) => {
              const meta = typeMeta(type);
              return (
                <li key={type} className="grid grid-cols-[8rem_minmax(0,1fr)_3rem] items-center gap-2 text-sm text-ink">
                  <span>
                    <span aria-hidden="true">{meta.icon} </span>
                    {typeLabel(t, type, n, lang)}
                  </span>
                  <span aria-hidden="true" className="h-3 rounded-full bg-surface-alt">
                    <span
                      className={`block h-3 rounded-full ${meta.swatch}`}
                      style={{ width: `${total > 0 ? Math.max(4, (n / total) * 100) : 0}%` }}
                    />
                  </span>
                  <span className="text-right font-semibold tabular-nums">{fmtNum(n, lang)}</span>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <DayChart series={data.series} />

      <section aria-labelledby="priv-recent-h" className="space-y-3">
        <h2 id="priv-recent-h" className="text-lg font-bold text-ink">
          {t("privacy.admin.recent")}
        </h2>
        <p className="text-sm text-muted">{t("privacy.admin.payloadOnly")}</p>
        {data.recent.length === 0 ? (
          <EmptyState title={t("privacy.admin.recentEmpty")} />
        ) : (
          <ul className="space-y-2" data-testid="privacy-recent">
            {data.recent.map((r) => (
              <li key={r.id}>
                <RecordRow record={r} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <ProvePanel trace={data.trace} />
    </>
  );
}

function DayChart({ series }: { series: PrivacyOverview["series"] }) {
  const t = useT();
  const { lang } = useLang();
  const [table, setTable] = useState(false);
  // plotting coordinates only: counts are server values
  const data = series.map((p) => ({ day: p.day.slice(5), protected: p.protected }));
  return (
    <Card as="section" labelledBy="priv-chart-h" className="space-y-3">
      <h2 id="priv-chart-h" className="text-lg font-bold text-ink">
        {t("privacy.admin.chart")}
      </h2>
      {series.length === 0 ? (
        <p className="text-sm text-muted">{t("privacy.admin.noData")}</p>
      ) : (
        <>
          <div role="img" aria-label={t("privacy.admin.chart")} className="h-48 w-full" data-testid="privacy-chart">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
                <XAxis dataKey="day" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} width={32} />
                <Tooltip />
                <Bar
                  dataKey="protected"
                  name={t("privacy.admin.protected")}
                  fill="var(--color-chart-1)"
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <button
            type="button"
            aria-expanded={table}
            onClick={() => setTable((v) => !v)}
            className={`rounded-md text-sm font-semibold text-brand-700 underline ${focusRing}`}
          >
            {t(table ? "privacy.admin.chartHide" : "privacy.admin.chartShow")}
          </button>
          {table ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-60 text-sm" data-testid="privacy-series-table">
                <caption className="sr-only">{t("privacy.admin.chart")}</caption>
                <thead>
                  <tr className="border-b border-line text-muted">
                    <th scope="col" className={th}>{t("privacy.admin.day")}</th>
                    <th scope="col" className={`${th} text-right`}>{t("privacy.admin.protected")}</th>
                    <th scope="col" className={`${th} text-right`}>{t("privacy.admin.leaked")}</th>
                  </tr>
                </thead>
                <tbody>
                  {series.map((p) => (
                    <tr key={p.day} className="border-b border-line last:border-0">
                      <th scope="row" className={`${td} text-left font-normal`}>{formatDate(p.day, lang)}</th>
                      <td className={`${td} text-right tabular-nums`}>{fmtNum(p.protected, lang)}</td>
                      <td className={`${td} text-right tabular-nums`}>{fmtNum(p.leaked, lang)}</td>
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

function RecordRow({ record: r }: { record: PrivacyRecord }) {
  const t = useT();
  const { lang } = useLang();
  const [open, setOpen] = useState(false);
  const panel = `priv-payload-${r.id}`;
  return (
    <Card className="space-y-2" >
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold text-ink">{r.node}</span>
        <span className="text-muted">
          {t("privacy.admin.source")}: {r.source}
        </span>
        <span className="text-muted">{formatDate(r.created_at.slice(0, 10), lang)}</span>
        {r.model ? <span className="text-muted">{r.model}</span> : null}
        <PrivacyBadge kind="protected" count={r.protected} />
        <PrivacyBadge kind="leaked" count={r.leaked} />
        {r.sent ? (
          <Badge tone="info" icon="➤">
            {t("privacy.admin.sent")}
          </Badge>
        ) : (
          <PrivacyBadge kind="notSent" />
        )}
      </div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => setOpen((v) => !v)}
        className={`min-h-6 rounded-md text-sm font-semibold text-brand-700 underline ${focusRing}`}
      >
        {t(open ? "privacy.admin.collapse" : "privacy.admin.expand")}
      </button>
      {open ? (
        <div
          id={panel}
          className="max-h-64 overflow-auto rounded-xl border border-line bg-surface-alt p-3 text-ink"
          data-testid="masked-payload"
        >
          <SegmentText segments={tokenize(r.masked_payload)} mono />
        </div>
      ) : null}
    </Card>
  );
}

function ProvePanel({ trace }: { trace: PrivacyOverview["trace"] }) {
  const t = useT();
  return (
    <Card as="section" labelledBy="priv-prove-h" className="space-y-2">
      <h2 id="priv-prove-h" className="text-lg font-bold text-ink">
        {t("privacy.admin.prove.title")}
      </h2>
      {trace.enabled && trace.url ? (
        <>
          <p className="text-sm text-ink">{t("privacy.admin.prove.explain")}</p>
          <a
            href={trace.url}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="trace-link"
            className={`inline-block rounded-md font-semibold text-brand-700 underline ${focusRing}`}
          >
            {t("privacy.admin.prove.link")} <span aria-hidden="true">↗</span>
          </a>
        </>
      ) : (
        <>
          <p className="text-sm text-ink" data-testid="trace-off">
            {trace.note || t("privacy.admin.prove.off")}
          </p>
          <p className="text-sm text-muted">{t("privacy.admin.prove.hint")}</p>
        </>
      )}
    </Card>
  );
}
