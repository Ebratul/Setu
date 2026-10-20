"use client";

import { SupplierDocBadge } from "@/components/documents/DocStatusBadge";
import { UploadPanel } from "@/components/documents/UploadPanel";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import {
  SUPPLIER_DOC_TYPES,
  listDocuments,
  supplierStatus,
} from "@/lib/api/documents";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { Bi } from "./Bi";

/** Supplier upload + status-only list: no score, findings, fields or hidden text are ever requested or shown. */
export function SupplierDocuments({ dealId, onChanged }: { dealId: string; onChanged?: () => void }) {
  const t = useT();
  const { lang } = useLang();
  const docs = useApi((s) => listDocuments(dealId, s), `sp-docs|${dealId}`);
  return (
    <section aria-labelledby="sp-doc-h" className="space-y-3">
      <h2 id="sp-doc-h" className="text-lg font-bold text-ink">
        <Bi k="sp.documents" />
      </h2>
      <UploadPanel
        dealId={dealId}
        supplier
        allowedTypes={SUPPLIER_DOC_TYPES}
        onChanged={() => {
          docs.reload();
          onChanged?.();
        }}
      />
      <Card>
        {docs.error ? (
          <QueryError error={docs.error} onRetry={docs.reload} />
        ) : !docs.data ? (
          <Skeleton className="h-16" />
        ) : docs.data.documents.length === 0 ? (
          <p className="text-sm text-muted">{t("sp.noDocuments")}</p>
        ) : (
          <ul className="divide-y divide-line" data-testid="sp-doc-list">
            {docs.data.documents.map((d) => (
              <li key={d.id} data-testid="sp-doc" className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                <span className="min-w-0 flex-1 basis-48">
                  <span className="font-semibold text-ink">{t(`docType.${d.doc_type}`)}</span>
                  <span className="block text-xs break-all text-muted">{d.file_name}</span>
                </span>
                {d.uploaded_at ? (
                  <span className="text-xs text-muted">{formatDate(d.uploaded_at.slice(0, 10), lang)}</span>
                ) : null}
                <SupplierDocBadge status={supplierStatus(d)} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </section>
  );
}
