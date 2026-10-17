"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import {
  acceptReference,
  docUiStatus,
  getDocument,
  getHiddenText,
  isChecking,
  recheckDocument,
  uploadErrorKey,
  type DocumentDetail,
  type HiddenTextOut,
} from "@/lib/api/documents";
import { getDocumentRegistry } from "@/lib/api/registry";
import { useApi } from "@/lib/useApi";

import { ChecksList } from "./ChecksList";
import { DocStatusBadge } from "./DocStatusBadge";
import { FieldsTable } from "./FieldsTable";
import { HiddenTextPanel } from "./HiddenTextPanel";
import { PreviewPane } from "./PreviewPane";
import { RegistryBox } from "./RegistryBox";
import { VerdictPanel } from "./VerdictPanel";

const linkCls =
  "text-sm font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function DocumentViewerPage({ id }: { id: string }) {
  const doc = useApi((s) => getDocument(id, s), `document|${id}`);
  const reload = doc.reload;
  const checking = doc.data ? isChecking(doc.data) : false;

  useEffect(() => {
    if (!checking) return;
    const timer = setInterval(reload, 2500);
    const stop = setTimeout(() => clearInterval(timer), 90_000);
    return () => {
      clearInterval(timer);
      clearTimeout(stop);
    };
  }, [checking, reload]);

  if (doc.error) return <QueryError error={doc.error} onRetry={doc.reload} />;
  if (!doc.data) return <Skeleton className="h-96" />;
  return <Viewer doc={doc.data} role={doc.data.viewer_role ?? null} reload={reload} />;
}

function Viewer({
  doc,
  role,
  reload,
}: {
  doc: DocumentDetail;
  role: string | null;
  reload: () => void;
}) {
  const t = useT();
  const [reveal, setReveal] = useState(false);
  const [hidden, setHidden] = useState<HiddenTextOut | null>(null);
  const [hiddenBusy, setHiddenBusy] = useState(false);
  const [hiddenError, setHiddenError] = useState<string | null>(null);
  const [recheckBusy, setRecheckBusy] = useState(false);
  const [recheckError, setRecheckError] = useState<string | null>(null);

  const [accepting, setAccepting] = useState(false);
  const [acceptBusy, setAcceptBusy] = useState(false);
  const [acceptError, setAcceptError] = useState<string | null>(null);

  const registry = useApi((s) => getDocumentRegistry(doc.id, s), `doc-registry|${doc.id}|${doc.check_status}`, role !== "SUPPLIER");
  const canRecheck = role === "BUYER" || role === "ADMIN";
  const buyerSide = role !== "SUPPLIER";
  const hasHidden = buyerSide && (doc.hidden_text_found === true || (doc.hidden_spans_count ?? 0) > 0);
  const status = docUiStatus(doc);
  const checkFailed = doc.warnings.includes("CHECK_FAILED");
  const refChanged = doc.findings.some((f) => f.check_code === "REFERENCE_CHANGED" && (f.status === "WARN" || f.status === "FAIL"));
  const canAccept =
    canRecheck &&
    doc.doc_type === "PROFORMA_INVOICE" &&
    !doc.reference_accepted &&
    (refChanged || doc.check_status === "WARNING");

  async function accept() {
    setAcceptBusy(true);
    setAcceptError(null);
    try {
      await acceptReference(doc.id);
      setAccepting(false);
      reload();
    } catch (e) {
      setAcceptError(t(uploadErrorKey(e)));
    } finally {
      setAcceptBusy(false);
    }
  }

  async function toggle() {
    if (reveal) {
      setReveal(false);
      return;
    }
    setReveal(true);
    if (hidden) return;
    setHiddenBusy(true);
    setHiddenError(null);
    try {
      setHidden(await getHiddenText(doc.id));
    } catch (e) {
      setHiddenError(e instanceof ApiError && e.status === 403 ? t("doc.hidden.forbidden") : t(uploadErrorKey(e)));
    } finally {
      setHiddenBusy(false);
    }
  }

  async function recheck() {
    setRecheckBusy(true);
    setRecheckError(null);
    setHidden(null);
    try {
      await recheckDocument(doc.id);
      reload();
    } catch (e) {
      setRecheckError(e instanceof ApiError && e.status === 403 ? t("doc.recheck.forbidden") : t(uploadErrorKey(e)));
    } finally {
      setRecheckBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <Link href={`/app/deals/${encodeURIComponent(doc.deal_reference)}`} className={linkCls}>
          ← {doc.deal_reference}
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t(`docType.${doc.doc_type}`)}</h1>
          <DocStatusBadge status={status} />
          <SimulatedBadge />
        </div>
        <p className="text-sm break-all text-muted" data-testid="doc-file-name">
          {doc.file_name}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          {hasHidden ? (
            <Button
              variant="secondary"
              aria-pressed={reveal}
              onClick={toggle}
              disabled={hiddenBusy}
              data-testid="reveal-hidden"
            >
              {hiddenBusy ? t("common.loading") : reveal ? t("doc.hidden.hide") : t("doc.hidden.reveal")}
            </Button>
          ) : null}
          {canRecheck ? (
            <Button onClick={recheck} disabled={recheckBusy} data-testid="recheck">
              {recheckBusy ? t("doc.recheck.busy") : t("doc.recheck.go")}
            </Button>
          ) : role === "JUDGE" ? (
            <span className="text-sm text-muted">{t("doc.readOnly")}</span>
          ) : null}
          {canAccept ? (
            <Button variant="secondary" onClick={() => setAccepting(true)} data-testid="accept-reference">
              {t("doc.accept.go")}
            </Button>
          ) : null}
          {doc.reference_accepted ? (
            <span className="text-sm font-semibold text-success" data-testid="reference-accepted">
              <span aria-hidden="true">✓ </span>
              {t("doc.accept.done")}
            </span>
          ) : null}
        </div>
        {checkFailed ? (
          <p role="alert" data-testid="check-failed" className="text-sm font-semibold text-danger">
            <span aria-hidden="true">✕ </span>
            {t("doc.checkFailed")}
          </p>
        ) : null}
        {recheckError ? (
          <p role="alert" className="text-sm font-medium text-danger">
            {recheckError}
          </p>
        ) : null}
      </header>

      <div role="status" aria-live="polite" className="sr-only">
        {isChecking(doc) ? t("doc.checkingLive") : t(`doc.status.${status}`)}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="min-w-0 space-y-4 lg:sticky lg:top-24 lg:self-start">
          <PreviewPane doc={doc} spans={reveal && hidden ? hidden.spans : null} onRefresh={reload} />
        </div>
        <div className="min-w-0 space-y-6">
          {reveal ? (
            hiddenError ? (
              <p role="alert" className="rounded-xl border border-danger bg-danger-soft p-3 text-sm font-medium text-danger">
                {hiddenError}
              </p>
            ) : hidden ? (
              <HiddenTextPanel hidden={hidden} />
            ) : null
          ) : null}

          <Card as="section" labelledBy="v-h" className="space-y-3">
            <h2 id="v-h" className="text-lg font-bold text-ink">
              {t("doc.verdict.title")}
            </h2>
            {doc.verdict ? (
              <VerdictPanel verdict={doc.verdict} />
            ) : (
              <p className="text-sm text-muted">
                {isChecking(doc) ? t("doc.checkingLive") : t("doc.verdict.none")}
              </p>
            )}
          </Card>

          {doc.fields ? (
            <Card as="section" labelledBy="f-h" className="space-y-3">
              <h2 id="f-h" className="text-lg font-bold text-ink">
                {t("doc.fields.title")}
              </h2>
              <FieldsTable fields={doc.fields} findings={doc.findings} />
            </Card>
          ) : null}

          {buyerSide && registry.data ? <RegistryBox registry={registry.data} /> : null}

          {buyerSide ? (
            <Card as="section" labelledBy="c-h" className="space-y-3">
              <h2 id="c-h" className="text-lg font-bold text-ink">
                {t("doc.checks.title")}
              </h2>
              <ChecksList findings={doc.findings} />
            </Card>
          ) : null}
        </div>
      </div>
      {accepting ? (
        <ConfirmDialog
          title={t("doc.accept.title")}
          confirmLabel={t("doc.accept.confirm")}
          busy={acceptBusy}
          error={acceptError}
          onConfirm={accept}
          onClose={() => setAccepting(false)}
        >
          <p>{t("doc.accept.body")}</p>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
