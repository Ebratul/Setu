"use client";

import Link from "next/link";

import { DocStatusBadge } from "@/components/documents/DocStatusBadge";
import { useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";
import type { DocUiStatus } from "@/lib/api/documents";

import { safeAppHref } from "../markdown";
import { CardShell } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "document_check" }>;

const UI: Record<string, DocUiStatus | null> = {
  PASSED: "PASSED",
  WARNING: "WARNING",
  FAILED: "FAILED",
  PENDING: "CHECKING",
  NOT_RUN: "UPLOADED",
  NONE: null,
};

const linkCls =
  "rounded-md font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

/** Read-only summary of stored document checks: status, score, top reasons and links. No actions. */
export function DocumentCheckCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const d = card.data;
  const status = UI[d.status] ?? null;
  const focus = d.focus;
  const reasons = (focus?.reasons ?? []).slice(0, 3);
  const flagged = d.instruction_from_document || d.hidden_text_found;
  return (
    <CardShell
      type="document_check"
      title={t("chat.card.docCheck", { ref: d.deal_ref })}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
      linkHref={focus?.route ?? d.deal_route}
      linkLabel={focus ? t("chat.card.openDocument") : t("chat.card.openDeal")}
    >
      <div className="flex flex-wrap items-center gap-2">
        {status ? <DocStatusBadge status={status} /> : <span className="text-sm text-muted">{t("doc.list.empty")}</span>}
        {d.score !== null ? (
          <span className="text-sm font-semibold text-ink tabular-nums" data-testid="doc-card-score">
            {t("doc.score", { n: d.score })}
          </span>
        ) : null}
        <span className="text-xs text-muted">
          {t("chat.card.docCounts", { passed: d.passed, warning: d.warning, failed: d.failed })}
        </span>
      </div>
      {flagged ? (
        <p role="alert" className="text-sm font-semibold text-danger" data-testid="doc-card-instruction">
          <span aria-hidden="true">■ </span>
          {t("doc.hidden.instruction")}
        </p>
      ) : null}
      {reasons.length > 0 ? (
        <ul className="space-y-1 text-sm text-ink">
          {reasons.map((r) => (
            <li key={r.code} className="flex gap-2">
              <span aria-hidden="true" className={r.status === "FAIL" ? "text-danger" : "text-warning"}>
                {r.status === "FAIL" ? "✕" : "▲"}
              </span>
              <span>{lang === "bn" ? r.detail_bn : r.detail_en}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {d.documents.length > 1 ? (
        <ul className="space-y-1 text-sm" data-testid="doc-card-list">
          {d.documents.slice(0, 8).map((x) => {
            const href = safeAppHref(x.route);
            const label = lang === "bn" ? x.doc_label_bn : x.doc_label_en;
            const s = UI[x.status];
            return (
              <li key={x.document_id} className="flex flex-wrap items-center gap-2">
                {href ? (
                  <Link href={href} className={linkCls}>
                    {label}
                  </Link>
                ) : (
                  <span>{label}</span>
                )}
                {s ? <DocStatusBadge status={s} /> : null}
                {x.score !== null ? <span className="text-xs text-muted">{t("doc.score", { n: x.score })}</span> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </CardShell>
  );
}
