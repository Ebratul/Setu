"use client";

import { useState } from "react";

import { Badge, type Tone } from "@/components/ui/Badge";
import { useLang, useT } from "@/i18n";
import type { RiskKind, TraceItem } from "@/lib/api/risk";

import { pick } from "./riskText";

type Props = { trace: TraceItem[] };

const KIND: Record<RiskKind, { tone: Tone; icon: string }> = {
  BLOCK: { tone: "danger", icon: "⛔" },
  TIER3: { tone: "danger", icon: "⚠" },
  TIER2: { tone: "warning", icon: "▲" },
};

export function RuleTrace({ trace }: Props) {
  const t = useT();
  const [showAll, setShowAll] = useState(false);
  const fired = trace.filter((i) => i.fired).sort((a, b) => Number(b.deciding) - Number(a.deciding));
  const notFired = trace.filter((i) => !i.fired);
  if (trace.length === 0) return <p className="text-sm text-muted">{t("risk.trace.none")}</p>;
  return (
    <div className="space-y-2" data-testid="rule-trace" data-demo="risk-trace">
      {fired.length > 0 ? (
        <ul className="space-y-2">
          {fired.map((i) => (
            <TraceRow key={i.code} item={i} />
          ))}
        </ul>
      ) : null}
      {notFired.length > 0 ? (
        <>
          <button
            type="button"
            aria-expanded={showAll}
            onClick={() => setShowAll((v) => !v)}
            className="rounded-md text-sm font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            {t(showAll ? "risk.trace.hideNot" : "risk.trace.showNot", { n: notFired.length })}
          </button>
          {showAll ? (
            <ul className="space-y-2">
              {notFired.map((i) => (
                <TraceRow key={i.code} item={i} />
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function TraceRow({ item: i }: { item: TraceItem }) {
  const t = useT();
  const { lang } = useLang();
  const k = KIND[i.kind];
  const highlight = i.fired && i.deciding;
  return (
    <li
      data-testid={`trace-${i.code}`}
      data-fired={i.fired}
      data-deciding={highlight}
      className={`flex flex-wrap items-start gap-x-3 gap-y-1 rounded-xl border p-3 text-sm ${
        highlight ? "border-2 border-brand-700 bg-brand-50" : "border-line bg-surface"
      }`}
    >
      <span
        className={`flex items-center gap-1 font-semibold ${i.fired ? "text-danger" : "text-muted"}`}
      >
        <span aria-hidden="true">{i.fired ? "✓" : "✗"}</span>
        {t(i.fired ? "risk.trace.fired" : "risk.trace.notFired")}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold break-words text-ink">{pick(lang, i.label_en, i.label_bn)}</p>
        <p className="break-words text-muted">{pick(lang, i.value_en, i.value_bn)}</p>
        {highlight ? (
          <p className="mt-1 text-xs font-bold text-brand-text">
            <span aria-hidden="true">★ </span>
            {t(i.kind === "BLOCK" ? "risk.trace.decidingBlock" : "risk.trace.deciding")}
          </p>
        ) : null}
      </div>
      <Badge tone={k.tone} icon={k.icon}>
        {t(`risk.kind.${i.kind}`)}
      </Badge>
    </li>
  );
}
