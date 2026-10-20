"use client";

import { useMemo, useState, type ReactNode } from "react";

import { useT } from "@/i18n";

import { Icon } from "./Icon";

export type Column<Row> = {
  id: string;
  header: string;
  cell: (row: Row) => ReactNode;
  /** Plain value used for sorting; omit for a non-sortable column. */
  sortValue?: (row: Row) => string | number;
  align?: "left" | "right";
};

type Props<Row> = {
  caption: string;
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
};

/** Sortable table with a sticky header; below `md` each row becomes a labelled card. */
export function DataTable<Row>({ caption, columns, rows, rowKey }: Props<Row>) {
  const t = useT();
  const [sort, setSort] = useState<{ id: string; dir: 1 | -1 } | null>(null);
  const sorted = useMemo(() => {
    const col = columns.find((c) => c.id === sort?.id);
    if (!sort || !col?.sortValue) return rows;
    const val = col.sortValue;
    return [...rows].sort((a, b) => {
      const x = val(a);
      const y = val(b);
      return (x < y ? -1 : x > y ? 1 : 0) * sort.dir;
    });
  }, [rows, columns, sort]);

  function toggle(id: string) {
    setSort((s) => (s?.id === id ? (s.dir === 1 ? { id, dir: -1 } : null) : { id, dir: 1 }));
  }

  return (
    <>
      <div className="hidden max-h-[70vh] overflow-auto rounded-card bg-surface shadow-card md:block">
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="sticky top-0 bg-surface-alt text-left">
            <tr>
              {columns.map((c) => {
                const active = sort?.id === c.id;
                return (
                  <th
                    key={c.id}
                    scope="col"
                    aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : c.sortValue ? "none" : undefined}
                    className={`px-4 py-3 font-semibold text-muted ${c.align === "right" ? "text-right" : ""}`}
                  >
                    {c.sortValue ? (
                      <button
                        type="button"
                        onClick={() => toggle(c.id)}
                        className="inline-flex min-h-8 items-center gap-1 rounded focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                      >
                        {c.header}
                        <Icon name="chevronDown" size={14} className={active && sort.dir === -1 ? "rotate-180" : active ? "" : "opacity-40"} />
                        <span className="sr-only">{t("ui.table.sort")}</span>
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={rowKey(r)} className="border-t border-line">
                {columns.map((c) => (
                  <td key={c.id} className={`px-4 py-3 ${c.align === "right" ? "text-right" : ""}`}>
                    {c.cell(r)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul aria-label={caption} className="space-y-3 md:hidden">
        {sorted.map((r) => (
          <li key={rowKey(r)} className="rounded-card bg-surface p-4 shadow-card">
            <dl className="space-y-2 text-sm">
              {columns.map((c) => (
                <div key={c.id} className="flex justify-between gap-4">
                  <dt className="text-muted">{c.header}</dt>
                  <dd className="min-w-0 text-right font-medium break-words text-ink">{c.cell(r)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}
