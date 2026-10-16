"use client";

import { useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import { getSuppliers, type SupplierScore } from "@/lib/api/analysis";
import { useApi } from "@/lib/useApi";

import { SupplierRow } from "./SupplierRow";

type SortKey =
  | "name"
  | "kyb_status"
  | "score"
  | "on_time_rate_pct"
  | "dispute_rate_pct"
  | "price_index"
  | "your_deals_count";
type Dir = "asc" | "desc";

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: "name", label: "suppliers.col.name", numeric: false },
  { key: "kyb_status", label: "suppliers.col.kyb", numeric: false },
  { key: "score", label: "suppliers.col.score", numeric: true },
  { key: "on_time_rate_pct", label: "suppliers.col.onTime", numeric: true },
  { key: "dispute_rate_pct", label: "suppliers.col.dispute", numeric: true },
  { key: "price_index", label: "suppliers.col.priceIndex", numeric: true },
  { key: "your_deals_count", label: "suppliers.col.deals", numeric: true },
];

/** Sort ordering only — values are compared, never displayed or used as money. */
function compare(a: SupplierScore, b: SupplierScore, key: SortKey): number {
  const av = a[key];
  const bv = b[key];
  if (av === null && bv === null) return 0;
  if (av === null) return 1;
  if (bv === null) return -1;
  if (typeof av === "number" && typeof bv === "number") return av - bv;
  const numeric = COLUMNS.find((c) => c.key === key)?.numeric;
  if (numeric) return Number(av) - Number(bv);
  return String(av).localeCompare(String(bv));
}

export function SupplierScorecard() {
  const t = useT();
  const { data, error, reload } = useApi(getSuppliers, "suppliers");
  const [sort, setSort] = useState<{ key: SortKey; dir: Dir }>({
    key: "score",
    dir: "asc",
  });

  const rows = useMemo(() => {
    const list = [...(data?.suppliers ?? [])];
    list.sort((a, b) => {
      const nullsLast =
        a[sort.key] === null || b[sort.key] === null
          ? compare(a, b, sort.key)
          : null;
      if (nullsLast !== null) return nullsLast;
      return sort.dir === "asc"
        ? compare(a, b, sort.key)
        : -compare(a, b, sort.key);
    });
    return list;
  }, [data, sort]);

  if (error) return <QueryError error={error} onRetry={reload} />;
  if (!data) {
    return (
      <div aria-busy="true" className="space-y-2">
        <Skeleton className="h-10" />
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
      </div>
    );
  }
  if (data.suppliers.length === 0) {
    return <EmptyState title={t("suppliers.empty")} />;
  }

  function toggle(key: SortKey) {
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "asc" },
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">
        {t("suppliers.intro", { months: data.window_months })}
      </p>
      <div className="overflow-x-auto rounded-card bg-surface shadow-card">
        <table className="w-full min-w-208 text-sm">
          <caption className="sr-only">{t("suppliers.caption")}</caption>
          <thead>
            <tr className="border-b border-line text-left">
              {COLUMNS.map((c) => {
                const active = sort.key === c.key;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={
                      active
                        ? sort.dir === "asc"
                          ? "ascending"
                          : "descending"
                        : "none"
                    }
                    className="p-3 font-medium text-muted"
                  >
                    <button
                      type="button"
                      onClick={() => toggle(c.key)}
                      className="inline-flex items-center gap-1 rounded-md font-medium focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                    >
                      {t(c.label)}
                      <span aria-hidden="true">
                        {active ? (sort.dir === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <SupplierRow key={s.supplier_id} supplier={s} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
