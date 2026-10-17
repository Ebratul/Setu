"use client";

import { KybBadge } from "@/components/kyb/KybBadge";
import { useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";

import { CardShell } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "kyb" }>;

export function KybCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const d = card.data;
  const reasons = d.reasons.slice(0, 3);
  return (
    <CardShell
      type="kyb"
      title={t("chat.card.kyb", { name: d.supplier_name })}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
      linkHref={d.supplier_route}
      linkLabel={t("chat.card.openSupplier")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <KybBadge status={d.status} />
        <span className="text-xs text-muted">
          {t("chat.card.checksPassed", {
            passed: d.checks_passed,
            total: d.checks_total,
          })}
        </span>
      </div>
      {reasons.length === 0 ? (
        <p className="text-sm text-ink">{t("chat.card.allPassed")}</p>
      ) : (
        <ul className="space-y-1 text-sm text-ink">
          {reasons.map((r) => (
            <li key={r.code} className="flex gap-2">
              <span
                aria-hidden="true"
                className={r.status === "FAIL" ? "text-danger" : "text-warning"}
              >
                {r.status === "FAIL" ? "✕" : "▲"}
              </span>
              <span>{lang === "bn" ? r.detail_bn : r.detail_en}</span>
            </li>
          ))}
        </ul>
      )}
      {d.has_pending_change && d.pending_status ? (
        <p className="text-sm font-semibold text-warning">
          ▲{" "}
          {t("chat.card.pendingChange", { status: t(`kyb.${d.pending_status}`) })}
        </p>
      ) : null}
    </CardShell>
  );
}
