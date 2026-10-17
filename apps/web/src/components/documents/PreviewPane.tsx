"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { fileHref, isImageMime, type DocumentDetail, type HiddenSpan } from "@/lib/api/documents";

import { HiddenOverlay } from "./HiddenOverlay";

type Props = {
  doc: DocumentDetail;
  /** spans to outline; null while the hidden-text toggle is off */
  spans: HiddenSpan[] | null;
  /** refetch the detail to get a fresh signed URL */
  onRefresh: () => void;
};

const linkCls =
  "font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function PreviewPane({ doc, spans, onRefresh }: Props) {
  const t = useT();
  const href = fileHref(doc.file_inline_url ?? null);
  const downloadHref = fileHref(doc.file_url);
  const retried = useRef<string | null>(null);

  // Refresh just before the signed URL expires.
  useEffect(() => {
    if (!doc.file_url_expires_at) return;
    const ms = new Date(doc.file_url_expires_at).getTime() - Date.now() - 15_000;
    const id = setTimeout(onRefresh, Math.max(5_000, Math.min(ms, 2_000_000)));
    return () => clearTimeout(id);
  }, [doc.file_url_expires_at, onRefresh]);

  function failed() {
    if (retried.current === doc.file_inline_url) return;
    retried.current = doc.file_inline_url ?? null;
    onRefresh();
  }

  const download = downloadHref ? (
    <a href={downloadHref} download className={linkCls}>
      {t("doc.preview.download")}
    </a>
  ) : null;

  if (!href) {
    return (
      <div role="status" className="space-y-3 rounded-2xl border border-line bg-surface-alt p-6 text-sm text-ink">
        <p>{doc.file_inline_url === null || downloadHref ? t("doc.preview.downloadOnly") : t("doc.preview.unavailable")}</p>
        {download}
        <div>
          <Button variant="secondary" onClick={onRefresh}>
            {t("common.retry")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        data-testid="preview"
        className="relative w-full overflow-hidden rounded-2xl border border-line bg-surface-alt"
      >
        {isImageMime(doc.mime_type) ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element -- signed, short-lived API URL */}
            <img src={href} alt={t("doc.preview.alt")} onError={failed} className="block h-auto w-full" />
          </>
        ) : (
          <div className="aspect-[595/842] w-full">
            <object
              data={`${href}#toolbar=0&navpanes=0&view=FitH`}
              type="application/pdf"
              aria-label={t("doc.preview.alt")}
              className="absolute inset-0 h-full w-full"
              onError={failed}
            >
              <p className="p-4 text-sm text-ink">{t("doc.preview.noPdf")} {download}</p>
            </object>
          </div>
        )}
        {spans && !isImageMime(doc.mime_type) ? <HiddenOverlay spans={spans} /> : null}
      </div>
      <p className="text-xs text-muted">{download}</p>
      {spans && spans.length > 0 ? <p className="text-xs text-muted">{t("doc.preview.overlayNote")}</p> : null}
    </div>
  );
}
