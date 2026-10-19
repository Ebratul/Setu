"use client";

import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import { getInjectionEvents, resolveInjectionEvent, type InjectionEvent } from "@/lib/api/security";
import { useApi } from "@/lib/useApi";

import { InjectionScoreboard } from "./InjectionScoreboard";
import { RuleChips } from "./HighlightedText";
import { fmtDateTime } from "./secText";

const th = "px-3 py-2 text-left font-semibold";
const td = "px-3 py-2 align-top";
const focus =
  "focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";
const sel = `rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink ${focus}`;

export function EventsTable({
  rows,
  isAdmin,
  onResolve,
  busyId,
}: {
  rows: readonly InjectionEvent[];
  isAdmin: boolean;
  onResolve: (id: string) => void;
  busyId: string | null;
}) {
  const t = useT();
  const { lang } = useLang();
  return (
    <div className="overflow-x-auto rounded-card bg-surface shadow-card">
      <table className="w-full text-sm text-ink" data-testid="events-table">
        <caption className="sr-only">{t("sec.admin.events")}</caption>
        <thead className="bg-surface-alt">
          <tr>
            <th scope="col" className={th}>{t("sec.admin.col.time")}</th>
            <th scope="col" className={th}>{t("sec.admin.col.source")}</th>
            <th scope="col" className={th}>{t("sec.admin.col.rules")}</th>
            <th scope="col" className={th}>{t("sec.admin.col.deal")}</th>
            <th scope="col" className={th}>{t("sec.admin.col.tool")}</th>
            <th scope="col" className={th}>{t("sec.admin.col.action")}</th>
            <th scope="col" className={th}>{t("sec.admin.col.layer")}</th>
            <th scope="col" className={th}>{t("sec.admin.col.origin")}</th>
            <th scope="col" className={th}>{t("sec.admin.col.audit")}</th>
            {isAdmin ? <th scope="col" className={th}>{t("sec.admin.col.resolve")}</th> : null}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr key={r.id} data-testid="event-row">
              <td className={`${td} whitespace-nowrap`}>{fmtDateTime(r.ts, lang)}</td>
              <td className={td}>
                <span className="rounded-full border border-line bg-surface-alt px-2 py-0.5 text-xs font-semibold">
                  {t(`sec.source.${r.source}`) === `sec.source.${r.source}` ? r.source : t(`sec.source.${r.source}`)}
                </span>
              </td>
              <td className={td}>
                <RuleChips rules={r.rules} />
                {r.snippet ? <p className="mt-1 max-w-xs text-xs break-words text-muted">{r.snippet}</p> : null}
              </td>
              <td className={td}>
                {r.deal_id ? (
                  <Link href={`/app/deals/${r.deal_id}`} className={`font-semibold text-brand-700 underline ${focus}`}>
                    {r.deal_reference ?? r.deal_id}
                  </Link>
                ) : (
                  "—"
                )}
                {r.flags_deal && !r.resolved ? (
                  <div className="mt-1">
                    <Badge tone="danger" icon="⚠">
                      {t("sec.admin.tier3")}
                    </Badge>
                  </div>
                ) : null}
              </td>
              <td className={`${td} font-mono`}>{r.tool ?? "—"}</td>
              <td className={td}>{r.action_taken}</td>
              <td className={td}>{r.layer ?? "—"}</td>
              <td className={td}>{r.origin}</td>
              <td className={td}>
                {r.audit_seq != null ? (
                  <span title={t("sec.admin.auditHint")}>{t("sec.admin.audit", { seq: r.audit_seq })}</span>
                ) : (
                  "—"
                )}
              </td>
              {isAdmin ? (
                <td className={td}>
                  {r.resolved ? (
                    <Badge tone="success" icon="✓">
                      {t("sec.admin.resolved")}
                    </Badge>
                  ) : (
                    <Button variant="secondary" disabled={busyId === r.id} onClick={() => onResolve(r.id)}>
                      {t("sec.admin.resolve")}
                    </Button>
                  )}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SecurityAdminPage() {
  const t = useT();
  const me = useApi((s) => getMe(s), "me");
  const [style, setStyle] = useState("");
  const [source, setSource] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const events = useApi(
    (s) => getInjectionEvents({ style: style || undefined, source: source || undefined }, s),
    `inj-events:${style}:${source}`,
  );
  const isAdmin = me.data?.role === "ADMIN";

  async function resolve(id: string) {
    setBusyId(id);
    setErr(null);
    try {
      await resolveInjectionEvent(id);
      events.reload();
    } catch (e) {
      setErr(e);
    } finally {
      setBusyId(null);
    }
  }

  const styles = Object.keys(events.data?.by_style ?? {}).sort();
  const sources = Object.keys(events.data?.by_source ?? {}).sort();
  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("sec.admin.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="text-muted">{t("sec.admin.intro")}</p>
        <Link
          href="/demo/attack-console"
          className={`inline-block font-semibold text-brand-700 underline ${focus}`}
        >
          {t("sec.admin.console")}
        </Link>
      </header>

      <InjectionScoreboard />

      <section aria-labelledby="ev-h" className="space-y-3">
        <h2 id="ev-h" className="text-lg font-bold text-ink">
          {t("sec.admin.events")}
        </h2>
        <div className="flex flex-wrap gap-4">
          <div className="space-y-1">
            <label htmlFor="ev-style" className="block text-sm font-semibold text-ink">
              {t("sec.admin.filterStyle")}
            </label>
            <select id="ev-style" value={style} onChange={(e) => setStyle(e.target.value)} className={sel}>
              <option value="">{t("sec.admin.all")}</option>
              {styles.map((s) => (
                <option key={s} value={s}>
                  {s} ({events.data?.by_style[s]})
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor="ev-source" className="block text-sm font-semibold text-ink">
              {t("sec.admin.filterSource")}
            </label>
            <select id="ev-source" value={source} onChange={(e) => setSource(e.target.value)} className={sel}>
              <option value="">{t("sec.admin.all")}</option>
              {sources.map((s) => (
                <option key={s} value={s}>
                  {s} ({events.data?.by_source[s]})
                </option>
              ))}
            </select>
          </div>
        </div>
        {err ? <QueryError error={err} /> : null}
        {events.error ? (
          <QueryError error={events.error} onRetry={events.reload} />
        ) : !events.data ? (
          <Skeleton className="h-48" />
        ) : events.data.items.length === 0 ? (
          <EmptyState title={t("sec.admin.empty")} />
        ) : (
          <EventsTable rows={events.data.items} isAdmin={isAdmin} onResolve={resolve} busyId={busyId} />
        )}
      </section>
    </div>
  );
}
