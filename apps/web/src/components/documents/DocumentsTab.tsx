"use client";

import Link from "next/link";
import { useId } from "react";

import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import type { DealDetail } from "@/lib/api/deals";
import {
  docUiStatus,
  listDocuments,
  type DocumentOut,
} from "@/lib/api/documents";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { DocStatusBadge } from "./DocStatusBadge";
import { UploadPanel } from "./UploadPanel";

const linkCls =
  "font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

type Props = { deal: DealDetail; onChanged: () => void };

export function DocumentsTab({ deal, onChanged }: Props) {
  const t = useT();
  const sig = deal.milestones.map((m) => m.evidence_status).join();
  const docs = useApi((s) => listDocuments(deal.id, s), `docs|${deal.id}|${sig}`);
  const canUpload = deal.viewer_role === "BUYER" || deal.viewer_role === "ADMIN";

  return (
    <div className="space-y-6">
      {canUpload ? (
        <UploadPanel
          dealId={deal.id}
          onChanged={() => {
            docs.reload();
            onChanged();
          }}
        />
      ) : (
        <p className="text-sm text-muted">{t("doc.readOnly")}</p>
      )}
      <Checklist deal={deal} />
      <section aria-labelledby="doc-list-h" className="space-y-3">
        <h2 id="doc-list-h" className="text-lg font-bold text-ink">
          {t("doc.list.title")}
        </h2>
        {docs.error ? (
          <QueryError error={docs.error} onRetry={docs.reload} />
        ) : !docs.data ? (
          <Skeleton className="h-24" />
        ) : docs.data.documents.length === 0 ? (
          <Card>
            <p className="text-sm text-muted">{t("doc.list.empty")}</p>
          </Card>
        ) : (
          <ul className="space-y-3" data-testid="doc-list">
            {docs.data.documents.map((d) => (
              <DocRow key={d.id} doc={d} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Checklist({ deal }: { deal: DealDetail }) {
  const t = useT();
  const id = useId();
  if (deal.milestones.length === 0) return null;
  return (
    <section aria-labelledby={`${id}-h`} className="space-y-3">
      <h2 id={`${id}-h`} className="text-lg font-bold text-ink">
        {t("doc.check.title")}
      </h2>
      <div className="grid gap-3 md:grid-cols-3">
        {deal.milestones.map((m) => (
          <Card key={m.id} as="section" className="space-y-2" labelledBy={`${id}-m${m.seq}`}>
            <h3 id={`${id}-m${m.seq}`} className="text-base font-bold text-ink">
              {t("ms.step", { seq: m.seq })} · {t(`trigger.${m.trigger}`)}
            </h3>
            <ul className="space-y-1.5 text-sm" data-testid="evidence-list">
              {m.required_evidence.map((e) => {
                const done = e.status === "VERIFIED";
                const bad = e.status === "REJECTED" || e.status === "FLAGGED";
                return (
                  <li key={e.doc_type} data-status={e.status} className="flex flex-wrap items-center gap-x-2">
                    <span
                      aria-hidden="true"
                      className={done ? "text-success" : bad ? "text-danger" : "text-muted"}
                    >
                      {done ? "☑" : bad ? "▲" : "☐"}
                    </span>
                    <span className="font-semibold text-ink">{t(`docType.${e.doc_type}`)}</span>
                    <span className="text-xs text-muted">
                      {t(`ms.ev.${e.status}`)} · {t("ms.docCount", { n: e.documents })}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Card>
        ))}
      </div>
    </section>
  );
}

function DocRow({ doc }: { doc: DocumentOut }) {
  const t = useT();
  const { lang } = useLang();
  const status = docUiStatus(doc);
  const top = doc.top_reason;
  return (
    <li data-testid="doc-row" data-status={status}>
      <Card className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-56">
          <p className="font-semibold text-ink">{t(`docType.${doc.doc_type}`)}</p>
          <p className="text-xs break-all text-muted">{doc.file_name}</p>
          {doc.uploaded_at ? (
            <p className="text-xs text-muted">{formatDate(doc.uploaded_at.slice(0, 10), lang)}</p>
          ) : null}
        </div>
        <DocStatusBadge status={status} />
        {doc.score !== null ? (
          <span className="text-sm text-ink tabular-nums" data-testid="doc-score">
            {t("doc.score", { n: doc.score })}
          </span>
        ) : null}
        {top ? (
          <p className="basis-full text-sm text-ink" data-testid="doc-top-reason">
            <span aria-hidden="true">{top.status === "FAIL" ? "✕ " : "▲ "}</span>
            {lang === "bn" ? top.issue_bn : top.issue_en}
          </p>
        ) : null}
        <Link href={`/app/documents/${doc.id}`} className={linkCls}>
          {t("doc.open")} <span aria-hidden="true">→</span>
        </Link>
      </Card>
    </li>
  );
}
