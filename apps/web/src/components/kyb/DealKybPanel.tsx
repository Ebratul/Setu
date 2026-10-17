"use client";

import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getSupplier, type KybCheck } from "@/lib/api/kyb";
import { useApi } from "@/lib/useApi";

import { KybBadge } from "./KybBadge";

export function topReasons(checks: KybCheck[], n = 3): KybCheck[] {
  const rank = { FAIL: 0, WARN: 1, PASS: 2 } as const;
  return checks
    .filter((c) => c.status !== "PASS")
    .sort((a, b) => rank[a.status] - rank[b.status])
    .slice(0, n);
}

export function DealKybPanel({ supplierId }: { supplierId: string }) {
  const t = useT();
  const { lang } = useLang();
  const profile = useApi((s) => getSupplier(supplierId, s), `supplier|${supplierId}`);

  if (profile.error) {
    return (
      <Card>
        <p className="text-sm text-muted">{t("sup.panel.unavailable")}</p>
      </Card>
    );
  }
  if (!profile.data) return <Skeleton className="h-28" />;
  const kyb = profile.data.kyb;
  const reasons = topReasons(kyb.checks);
  return (
    <Card as="section" labelledBy="deal-kyb-h" className="space-y-3">
      {kyb.status === "BLOCKED" ? (
        <div
          role="alert"
          data-testid="kyb-blocked-banner"
          className="flex gap-2 rounded-xl border-2 border-danger bg-danger-soft p-3 text-sm font-semibold text-danger"
        >
          <span aria-hidden="true">✕</span>
          {t("sup.panel.blocked")}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="deal-kyb-h" className="text-lg font-bold text-ink">
          {t("sup.panel.title")}
        </h2>
        <KybBadge status={kyb.status} />
      </div>
      {reasons.length === 0 ? (
        <p className="text-sm text-ink">{t("sup.panel.allPassed")}</p>
      ) : (
        <ul className="space-y-1 text-sm text-ink">
          {reasons.map((c) => (
            <li key={c.code} className="flex gap-2">
              <span
                aria-hidden="true"
                className={c.status === "FAIL" ? "text-danger" : "text-warning"}
              >
                {c.status === "FAIL" ? "✕" : "▲"}
              </span>
              <span>{lang === "bn" ? c.detail_bn : c.detail_en}</span>
            </li>
          ))}
        </ul>
      )}
      <Link
        href={`/app/suppliers/${profile.data.supplier_id}`}
        className="inline-block rounded text-sm font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        {t("sup.panel.viewProfile")} →
      </Link>
    </Card>
  );
}
