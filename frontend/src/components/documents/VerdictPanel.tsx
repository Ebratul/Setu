"use client";

import { useLang, useT } from "@/i18n";
import type { VerdictOut } from "@/lib/api/documents";

const BAR = (s: number) => (s > 60 ? "bg-danger" : s >= 30 ? "bg-warning" : "bg-success");

/** Server-computed risk score (higher = riskier) and fixed-template explanation. */
export function VerdictPanel({ verdict }: { verdict: VerdictOut }) {
  const t = useT();
  const { lang } = useLang();
  const score = Math.max(0, Math.min(100, verdict.score));
  return (
    <div className="space-y-2" data-testid="verdict">
      <div
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
        aria-label={t("doc.verdict.meter", { n: score })}
        className="flex items-center gap-3"
      >
        <div className="h-3 min-w-0 flex-1 overflow-hidden rounded-full bg-line">
          <div className={`h-full ${BAR(score)}`} style={{ width: `${score}%` }} />
        </div>
        <span className="text-lg font-bold text-ink tabular-nums">{score}/100</span>
      </div>
      <p className="text-xs text-muted">{t("doc.verdict.scale")}</p>
      <p className="text-sm text-ink">{lang === "bn" ? verdict.explanation_bn : verdict.explanation_en}</p>
    </div>
  );
}
