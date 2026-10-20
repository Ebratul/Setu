"use client";

import { useLang, useT } from "@/i18n";
import type { RiskHint } from "@/lib/api/risk";

import { pick } from "./riskText";

type Props = { hints: RiskHint[] };

export function RiskHints({ hints }: Props) {
  const t = useT();
  const { lang } = useLang();
  if (hints.length === 0) return null;
  return (
    <section aria-label={t("risk.hints.title")} className="space-y-2" data-testid="risk-hints">
      <h3 className="text-sm font-bold text-ink">{t("risk.hints.title")}</h3>
      <ul className="space-y-1 text-sm">
        {hints.map((h) => (
          <li key={h.code} className="flex flex-wrap items-baseline gap-2" data-testid={`hint-${h.code}`}>
            <span aria-hidden="true">{h.to_tier === null ? "•" : "↓"}</span>
            <span className={h.to_tier === null ? "text-muted" : "text-ink"}>
              {pick(lang, h.text_en, h.text_bn)}
            </span>
            {h.to_tier !== null ? (
              <span className="rounded-full border border-success bg-success-soft px-2 py-0.5 text-xs font-semibold text-success">
                {t("risk.hints.toTier", { tier: h.to_tier })}
              </span>
            ) : (
              <span className="rounded-full border border-line bg-surface-alt px-2 py-0.5 text-xs font-semibold text-muted">
                {t("risk.hints.blocked")}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
