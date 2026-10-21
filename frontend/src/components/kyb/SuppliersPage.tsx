"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getSuppliers, type SupplierListItem } from "@/lib/api/kyb";
import { formatDate, formatPct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { KybBadge } from "./KybBadge";
import { ScoreBar } from "./ScoreBar";

const FILTERS = ["ALL", "VERIFIED", "WARNING", "BLOCKED", "PENDING"] as const;
type Filter = (typeof FILTERS)[number];

const field =
  "w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

function SupplierCard({ s }: { s: SupplierListItem }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <li data-testid="supplier-row" data-code={s.code} data-status={s.kyb_badge}>
      <Card className="h-full space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-base font-bold break-words text-ink">
              <Link
                href={`/app/suppliers/${s.supplier_id}`}
                className="rounded underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                {s.name}
              </Link>
            </h2>
            <p className="text-sm text-muted">
              {s.city}, {s.country}
            </p>
          </div>
          <KybBadge status={s.kyb_badge} />
        </div>
        {s.has_pending_change ? (
          <p
            data-testid="pending-marker"
            className="inline-flex items-center gap-1 rounded-full border border-warning bg-warning-soft px-2.5 py-0.5 text-xs font-semibold text-warning"
          >
            <span aria-hidden="true">⇄</span>
            {t("sup.pendingChange")}
          </p>
        ) : null}
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <dt className="text-muted">{t("sup.col.score")}</dt>
            <dd>
              <ScoreBar score={s.kyb_score} />
            </dd>
          </div>
          <div>
            <dt className="text-muted">{t("sup.col.deals")}</dt>
            <dd className="font-semibold text-ink">{s.completed_deals}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("sup.col.onTime")}</dt>
            <dd className="font-semibold text-ink">
              {s.on_time_rate_pct ? formatPct(s.on_time_rate_pct, lang) : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted">{t("sup.col.lastChecked")}</dt>
            <dd className="font-semibold text-ink">
              {s.last_checked
                ? formatDate(s.last_checked.slice(0, 10), lang)
                : t("sup.never")}
            </dd>
          </div>
        </dl>
      </Card>
    </li>
  );
}

export function SuppliersPage() {
  const t = useT();
  const { data, error, reload } = useApi(getSuppliers, "suppliers");
  const [status, setStatus] = useState<Filter>("ALL");
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (data?.suppliers ?? []).filter(
      (s) =>
        (status === "ALL" || s.kyb_badge === status) &&
        (!needle ||
          s.name.toLowerCase().includes(needle) ||
          s.city.toLowerCase().includes(needle)),
    );
  }, [data, status, q]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-ink">{t("sup.title")}</h1>
        <p className="text-muted">{t("sup.intro")}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="sup-search" className="mb-1 block text-sm font-semibold text-ink">
            {t("sup.search")}
          </label>
          <input
            id="sup-search"
            type="search"
            value={q}
            placeholder={t("sup.searchPlaceholder")}
            onChange={(e) => setQ(e.target.value)}
            className={field}
          />
        </div>
        <div>
          <label htmlFor="sup-filter" className="mb-1 block text-sm font-semibold text-ink">
            {t("sup.filter")}
          </label>
          <select
            id="sup-filter"
            value={status}
            onChange={(e) => setStatus(e.target.value as Filter)}
            className={field}
          >
            {FILTERS.map((f) => (
              <option key={f} value={f}>
                {f === "ALL" ? t("sup.all") : t(`kyb.${f}`)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div aria-live="polite">
        {error ? (
          <QueryError error={error} onRetry={reload} />
        ) : !data ? (
          <Skeleton className="h-48" />
        ) : data.suppliers.length === 0 ? (
          <EmptyState title={t("sup.empty")} />
        ) : rows.length === 0 ? (
          <EmptyState title={t("sup.noMatch")} />
        ) : (
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {rows.map((s) => (
              <SupplierCard key={s.supplier_id} s={s} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
