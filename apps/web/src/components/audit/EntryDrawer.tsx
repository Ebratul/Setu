"use client";

import { CopyChip } from "@/components/approvals/CopyChip";
import { TierBadge } from "@/components/risk/TierBadge";
import { Badge } from "@/components/ui/Badge";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { Modal } from "@/components/ui/Modal";
import { useLang, useT } from "@/i18n";
import { getAuditEntry } from "@/lib/api/audit";
import { isReceiptAction } from "@/lib/audit/receipt";
import { useApi } from "@/lib/useApi";

import { entryText, fmtTime } from "./auditText";
import { ReceiptButton } from "./ReceiptButton";

function Field({ label, value, copy }: { label: string; value: string; copy?: boolean }) {
  const t = useT();
  return (
    <div className="space-y-1">
      <dt className="flex items-center gap-2 text-xs font-semibold text-muted">
        {label}
        {copy ? (
          <CopyChip
            text={t("audit.copy")}
            copyValue={value}
            ariaLabel={t("audit.copyField", { field: label })}
            copiedLabel={t("audit.copied")}
          />
        ) : null}
      </dt>
      <dd>
        <code className="block rounded-lg bg-surface-alt p-2 font-mono text-xs break-all whitespace-pre-wrap text-ink">{value}</code>
      </dd>
    </div>
  );
}

/** Side detail for one entry: the exact hashed bytes, the chain hashes and the signature check. */
export function EntryDrawer({ seq, onClose }: { seq: number; onClose: () => void }) {
  const t = useT();
  const { lang } = useLang();
  const q = useApi((s) => getAuditEntry(seq, s), `audit-entry|${seq}`);
  const e = q.data;
  return (
    <Modal title={t("audit.drawer.title", { seq })} onClose={onClose}>
      {q.error ? (
        <QueryError error={q.error} onRetry={q.reload} />
      ) : !e ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="space-y-4" data-testid="entry-drawer">
          <div className="flex flex-wrap items-center gap-2">
            <TierBadge tier={e.tier} decision={e.decision} />
            {e.verified ? (
              <Badge tone="success" icon="✓">
                {t("audit.drawer.verified")}
              </Badge>
            ) : (
              <Badge tone="danger" icon="✕">
                {t("audit.drawer.notVerified")}
                {e.verify_reason ? ` (${e.verify_reason})` : ""}
              </Badge>
            )}
            {isReceiptAction(e.action) ? <ReceiptButton seq={e.seq} /> : null}
          </div>
          <p className="text-sm font-semibold text-ink">{entryText(e, lang)}</p>
          <p className="text-xs text-muted">
            {e.action} · {e.actor_type}:{e.actor_id} · {fmtTime(e.ts, lang)}
          </p>
          <dl className="space-y-3">
            <Field label={t("audit.drawer.canonical")} value={e.canonical} copy />
            <Field label={t("audit.drawer.payloadHash")} value={e.payload_hash} copy />
            <Field label={t("audit.drawer.prevHash")} value={e.prev_hash} copy />
            <Field label={t("audit.drawer.entryHash")} value={e.entry_hash} copy />
            <Field label={t("audit.drawer.signature")} value={e.signature} copy />
          </dl>
        </div>
      )}
    </Modal>
  );
}
