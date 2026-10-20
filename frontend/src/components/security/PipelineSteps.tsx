"use client";

import { useLang, useT } from "@/i18n";
import type { PipelineStep } from "@/lib/api/security";

import { pickText } from "./secText";

const ORDER: PipelineStep["id"][] = ["privacy", "wrap", "detector", "gating", "risk", "answer"];

/** The six defence stages in pipeline order; each shows ✓ or ✕ as an icon with a text label, never colour alone. */
export function PipelineSteps({ steps }: { steps: readonly PipelineStep[] }) {
  const t = useT();
  const { lang } = useLang();
  const sorted = [...steps].sort((a, b) => ORDER.indexOf(a.id) - ORDER.indexOf(b.id));
  return (
    <ol className="space-y-2" aria-label={t("sec.pipe.label")} data-testid="pipeline-steps">
      {sorted.map((s, i) => {
        const label = s.ok ? t("sec.pipe.ok") : t("sec.pipe.fail");
        return (
          <li
            key={s.id}
            data-testid={`step-${s.id}`}
            data-ok={s.ok}
            data-status={s.status}
            style={{ animationDelay: `${i * 350}ms` }}
            className={`sec-step flex gap-3 rounded-2xl border p-3 ${
              s.ok ? "border-success bg-success-soft" : "border-danger bg-danger-soft"
            }`}
          >
            <span
              role="img"
              aria-label={label}
              className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white ${
                s.ok ? "bg-success" : "bg-danger"
              }`}
            >
              <span aria-hidden="true">{s.ok ? "✓" : "✕"}</span>
            </span>
            <div className="min-w-0 space-y-0.5">
              <p className="flex flex-wrap items-center gap-2 text-sm font-bold text-ink">
                <span className="rounded-full border border-line bg-surface px-2 py-0.5 text-xs font-semibold text-muted">
                  {t("sec.pipe.layer", { n: s.layer })}
                </span>
                {pickText(lang, s.title_en, s.title_bn)}
                <span className="text-xs font-semibold text-muted">({t(`sec.pipe.status.${s.status}`)})</span>
              </p>
              <p className="text-sm break-words text-ink">{pickText(lang, s.detail_en, s.detail_bn)}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
