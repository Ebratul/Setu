"use client";

import { useId, useState } from "react";

import { useT } from "@/i18n";
import type { SecurityCheck } from "@/lib/api/security";

const TOOL_LABEL: Record<string, string> = {
  check_documents: "docs",
  search_knowledge: "kb",
  verify_party: "party",
  registry_status: "registry",
};

/** "Security check" disclosure under an assistant answer. Renders nothing when there is no check. */
export function SecurityCheckChip({ security }: { security?: SecurityCheck | null }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!security) return null;
  const checked = [...new Set((security.checked ?? []).map((n) => t(`sec.chip.tool.${TOOL_LABEL[n] ?? "other"}`)))];
  const ignored = security.ignored ?? [];
  const blocked = security.blocked_tools ?? [];
  const guard = security.guard ?? [];
  const attention = ignored.length > 0 || blocked.length > 0 || security.deal_flagged;
  return (
    <div data-testid="security-chip" className="text-xs">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
          attention ? "border-warning bg-warning-soft text-warning" : "border-success bg-success-soft text-success"
        }`}
      >
        <span aria-hidden="true">{attention ? "▲" : "🛡"}</span>
        {t("sec.chip.title")}
        <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open ? (
        <ul id={id} className="mt-2 space-y-1 rounded-xl border border-line bg-surface-alt p-3 text-ink">
          <li>{checked.length > 0 ? t("sec.chip.checked", { list: checked.join(", ") }) : t("sec.chip.checkedNone")}</li>
          {!security.defences ? <li className="font-semibold text-warning">{t("sec.chip.off")}</li> : null}
          {ignored.map((g, i) => (
            <li key={i}>
              {t(`sec.chip.ignored.${g.source}`) === `sec.chip.ignored.${g.source}`
                ? t("sec.chip.ignored.other")
                : t(`sec.chip.ignored.${g.source}`)}
              {g.rules.length > 0 ? <span className="font-mono text-muted"> ({g.rules.join(", ")})</span> : null}
            </li>
          ))}
          {blocked.map((b, i) => (
            <li key={`b${i}`} className="font-semibold">
              {t("sec.chip.blocked", { name: b.name })}
            </li>
          ))}
          {guard.length > 0 ? <li>{t("sec.chip.guard", { list: guard.join(", ") })}</li> : null}
          {security.deal_flagged ? (
            <li role="note" className="font-semibold text-danger">
              <span aria-hidden="true">⚠ </span>
              {t("sec.chip.flagged")}
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
