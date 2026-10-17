"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import {
  getRegistryStats,
  listRegistry,
  type RegistryEntry,
  type RegistryStats,
} from "@/lib/api/registry";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const PAGE_SIZE = 20;
type StatusF = "ALL" | "ACTIVE" | "RELEASED";
type ResultF = "ALL" | "EXACT_DUPLICATE" | "NEAR_DUPLICATE";

const th = "px-3 py-2 text-left font-semibold";
const td = "px-3 py-2 align-top";

export function RegistryAdminPage() {
  const t = useT();
  const [status, setStatus] = useState<StatusF>("ALL");
  const [result, setResult] = useState<ResultF>("ALL");
  const [offset, setOffset] = useState(0);

  const stats = useApi((s) => getRegistryStats(s), "registry-stats");
  const list = useApi(
    (s) =>
      listRegistry(
        {
          status: status === "ALL" ? undefined : status,
          result: result === "ALL" ? undefined : result,
          limit: PAGE_SIZE,
          offset,
        },
        s,
      ),
    `registry|${status}|${result}|${offset}`,
  );

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("reg.admin.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="text-muted">{t("reg.admin.intro")}</p>
      </header>

      {stats.error ? (
        <QueryError error={stats.error} onRetry={stats.reload} />
      ) : stats.data ? (
        <Counters stats={stats.data} />
      ) : (
        <Skeleton className="h-28" />
      )}

      <section aria-labelledby="reg-filters-h" className="flex flex-wrap items-end gap-4">
        <h2 id="reg-filters-h" className="sr-only">
          {t("reg.admin.filters")}
        </h2>
        <SegmentedControl<StatusF>
          legend={t("reg.admin.status")}
          value={status}
          onChange={(v) => {
            setStatus(v);
            setOffset(0);
          }}
          options={[
            { value: "ALL", label: t("reg.admin.all") },
            { value: "ACTIVE", label: t("reg.admin.statusActive") },
            { value: "RELEASED", label: t("reg.admin.statusReleased") },
          ]}
        />
        <SegmentedControl<ResultF>
          legend={t("reg.admin.result")}
          value={result}
          onChange={(v) => {
            setResult(v);
            setOffset(0);
          }}
          options={[
            { value: "ALL", label: t("reg.admin.all") },
            { value: "EXACT_DUPLICATE", label: t("reg.admin.resultExact") },
            { value: "NEAR_DUPLICATE", label: t("reg.admin.resultNear") },
          ]}
        />
      </section>

      <section aria-labelledby="reg-table-h" aria-busy={list.loading} className="space-y-3">
        <h2 id="reg-table-h" className="text-lg font-bold text-ink">
          {t("reg.admin.table")}
        </h2>
        {list.error ? (
          <QueryError error={list.error} onRetry={list.reload} />
        ) : !list.data ? (
          <Skeleton className="h-48" />
        ) : list.data.items.length === 0 ? (
          <EmptyState title={t("reg.admin.empty")} />
        ) : (
          <>
            <Card>
              <div className="overflow-x-auto">
                <table className="w-full min-w-208 text-sm" data-testid="registry-table">
                  <caption className="sr-only">{t("reg.admin.table")}</caption>
                  <thead>
                    <tr className="border-b border-line text-muted">
                      <th scope="col" className={th}>{t("reg.admin.hash")}</th>
                      <th scope="col" className={th}>{t("reg.admin.docType")}</th>
                      <th scope="col" className={th}>{t("reg.admin.purpose")}</th>
                      <th scope="col" className={th}>{t("reg.admin.lender")}</th>
                      <th scope="col" className={th}>{t("reg.admin.deal")}</th>
                      <th scope="col" className={th}>{t("reg.admin.registered")}</th>
                      <th scope="col" className={`${th} text-right`}>{t("reg.admin.seen")}</th>
                      <th scope="col" className={`${th} text-right`}>{t("reg.admin.hits")}</th>
                      <th scope="col" className={th}>{t("reg.admin.status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.data.items.map((e) => (
                      <Row key={e.id} entry={e} />
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Pager
              offset={offset}
              count={list.data.items.length}
              total={list.data.total}
              onChange={setOffset}
            />
          </>
        )}
      </section>
    </div>
  );
}

function Counters({ stats }: { stats: RegistryStats }) {
  const t = useT();
  const small: [string, number][] = [
    [t("reg.admin.entries"), stats.entries],
    [t("reg.admin.active"), stats.active],
    [t("reg.admin.released"), stats.released],
  ];
  return (
    <div className="grid gap-4 md:grid-cols-2" data-testid="registry-counters">
      <Card as="section" labelledBy="reg-dup-h" className="border-2 border-danger">
        <h2 id="reg-dup-h" className="text-sm font-semibold text-muted">
          {t("reg.admin.duplicates")}
        </h2>
        <p className="text-4xl font-bold text-danger tabular-nums" data-testid="duplicates-total">
          <span aria-hidden="true">■ </span>
          {stats.duplicates_blocked}
        </p>
        <p className="mt-1 text-sm text-ink">
          {t("reg.admin.exact")}: <strong data-testid="exact-total">{stats.exact_blocked}</strong>
          {" · "}
          {t("reg.admin.near")}: <strong data-testid="near-total">{stats.near_blocked}</strong>
        </p>
      </Card>
      <Card>
        <dl className="grid grid-cols-3 gap-3">
          {small.map(([k, v]) => (
            <div key={k}>
              <dt className="text-sm text-muted">{k}</dt>
              <dd className="text-2xl font-bold text-ink tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>
    </div>
  );
}

function Row({ entry: e }: { entry: RegistryEntry }) {
  const t = useT();
  const { lang } = useLang();
  const active = e.status === "ACTIVE";
  return (
    <tr className="border-b border-line last:border-0" data-testid="registry-row">
      <td className={`${td} font-mono text-xs`}>{e.sha256_prefix}</td>
      <td className={td}>{t(`docType.${e.doc_type}`)}</td>
      <td className={td}>
        <Badge tone={e.purpose === "FINANCING_COLLATERAL" ? "warning" : "info"} icon={e.purpose === "FINANCING_COLLATERAL" ? "◆" : "▣"}>
          {t(`reg.purpose.${e.purpose}`)}
        </Badge>
      </td>
      <td className={td}>{e.lender_name ?? "—"}</td>
      <td className={td}>{e.deal_ref ?? "—"}</td>
      <td className={td}>{formatDate(e.registered_on.slice(0, 10), lang)}</td>
      <td className={`${td} text-right tabular-nums`}>{e.seen_count}</td>
      <td className={`${td} text-right tabular-nums`}>
        {e.exact_hits} / {e.near_hits}
      </td>
      <td className={td}>
        <Badge tone={active ? "success" : "neutral"} icon={active ? "●" : "○"}>
          {t(active ? "reg.admin.statusActive" : "reg.admin.statusReleased")}
        </Badge>
      </td>
    </tr>
  );
}

function Pager({
  offset,
  count,
  total,
  onChange,
}: {
  offset: number;
  count: number;
  total: number;
  onChange: (o: number) => void;
}) {
  const t = useT();
  return (
    <nav aria-label={t("reg.admin.pagination")} className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted" aria-live="polite" data-testid="registry-range">
        {t("reg.admin.range", { from: offset + 1, to: offset + count, total })}
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}>
          {t("reg.admin.prev")}
        </Button>
        <Button variant="secondary" disabled={offset + PAGE_SIZE >= total} onClick={() => onChange(offset + PAGE_SIZE)}>
          {t("reg.admin.next")}
        </Button>
      </div>
    </nav>
  );
}
