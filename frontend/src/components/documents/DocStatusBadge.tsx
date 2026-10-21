"use client";

import { toneClasses, type Tone } from "@/components/ui/Badge";
import { Bi } from "@/components/supplier/Bi";
import { useT } from "@/i18n";
import type { DocUiStatus, SupplierStatus } from "@/lib/api/documents";

const META: Record<DocUiStatus, { tone: Tone; icon: string }> = {
  UPLOADED: { tone: "neutral", icon: "↑" },
  CHECKING: { tone: "info", icon: "…" },
  PASSED: { tone: "success", icon: "✓" },
  WARNING: { tone: "warning", icon: "▲" },
  FAILED: { tone: "danger", icon: "✕" },
  REJECTED: { tone: "danger", icon: "■" },
};

const SUPPLIER_META: Record<SupplierStatus, { tone: Tone; icon: string }> = {
  UPLOADED: { tone: "neutral", icon: "↑" },
  REVIEW: { tone: "info", icon: "…" },
  ACCEPTED: { tone: "success", icon: "✓" },
  ATTENTION: { tone: "warning", icon: "▲" },
};

const base =
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap";

/** Icon + text + colour, never colour alone. */
export function DocStatusBadge({ status }: { status: DocUiStatus }) {
  const t = useT();
  const m = META[status] ?? META.UPLOADED;
  return (
    <span data-testid="doc-status" data-status={status} className={`${base} ${toneClasses[m.tone]}`}>
      <span aria-hidden="true">{m.icon}</span>
      {t(`doc.status.${status}`)}
    </span>
  );
}

/** Supplier-facing status: no score or reason is ever part of it. */
export function SupplierDocBadge({ status }: { status: SupplierStatus }) {
  const m = SUPPLIER_META[status];
  return (
    <span data-testid="doc-status" data-status={status} className={`${base} ${toneClasses[m.tone]}`}>
      <span aria-hidden="true">{m.icon}</span>
      <Bi k={`doc.sup.${status}`} />
    </span>
  );
}
