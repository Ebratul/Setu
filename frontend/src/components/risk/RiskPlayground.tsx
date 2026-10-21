"use client";

import { useReducer } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { evaluateRisk, getRiskPolicy } from "@/lib/api/risk";
import { useApi, useDebounced } from "@/lib/useApi";

import { fmtInt } from "./riskText";
import { RiskDecisionCard } from "./RiskDecisionCard";

const MAX_AMOUNT = 60000;

type Facts = {
  amount: number;
  first_deal: boolean;
  beneficiary_change: boolean;
  beneficiary_changed_recently: boolean;
  fraud_score: number;
  duplicate_hash: boolean;
  hidden_instruction: boolean;
  sanctions_hit: boolean;
  document_warning: boolean;
  document_failed: boolean;
};
type BoolKey = {
  [K in keyof Facts]: Facts[K] extends boolean ? K : never;
}[keyof Facts];

const INITIAL: Facts = {
  amount: 9600,
  first_deal: false,
  beneficiary_change: false,
  beneficiary_changed_recently: false,
  fraud_score: 0,
  duplicate_hash: false,
  hidden_instruction: false,
  sanctions_hit: false,
  document_warning: false,
  document_failed: false,
};

const TOGGLES: { key: BoolKey; label: string }[] = [
  { key: "first_deal", label: "risk.pg.firstDeal" },
  { key: "beneficiary_change", label: "risk.pg.beneficiaryChange" },
  { key: "beneficiary_changed_recently", label: "risk.pg.recentAccount" },
  { key: "duplicate_hash", label: "risk.pg.duplicate" },
  { key: "hidden_instruction", label: "risk.pg.hidden" },
  { key: "sanctions_hit", label: "risk.pg.sanctions" },
  { key: "document_warning", label: "risk.pg.docWarning" },
  { key: "document_failed", label: "risk.pg.docFailed" },
];

function clamp(n: number, max: number) {
  return Number.isFinite(n) ? Math.min(Math.max(Math.round(n), 0), max) : 0;
}

type Action = { set: Partial<Facts> } | { reset: true };
const reducer = (s: Facts, a: Action): Facts => ("reset" in a ? INITIAL : { ...s, ...a.set });

export function RiskPlayground() {
  const t = useT();
  const { lang } = useLang();
  const [facts, dispatch] = useReducer(reducer, INITIAL);
  const debounced = useDebounced(facts, 250);
  const policy = useApi((s) => getRiskPolicy(s), "risk-policy");
  const result = useApi((s) => {
    const { amount, ...rest } = debounced;
    return evaluateRisk({ ...rest, amount_usd: String(amount) }, s);
  }, `risk-eval|${JSON.stringify(debounced)}`);
  const limit = Number(policy.data?.tier1_max_usd ?? "20000");
  const limitPct = Math.min(100, (limit / MAX_AMOUNT) * 100);
  const updating = result.loading || debounced !== facts;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("risk.pg.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="text-muted">{t("risk.pg.intro")}</p>
        <p
          className="inline-block rounded-xl border border-info bg-info-soft px-3 py-1 text-sm font-semibold text-info"
          data-testid="dry-run-note"
        >
          <span aria-hidden="true">ℹ </span>
          {t("risk.pg.dryRun")}
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Card as="section" labelledBy="pg-facts-h" className="space-y-5">
          <h2 id="pg-facts-h" className="text-lg font-bold text-ink">
            {t("risk.pg.facts")}
          </h2>

          <div className="space-y-2">
            <label htmlFor="pg-amount-range" className="block text-sm font-semibold text-ink">
              {t("risk.pg.amount")}
            </label>
            <input
              id="pg-amount-range"
              type="range"
              min={0}
              max={MAX_AMOUNT}
              step={100}
              value={facts.amount}
              onChange={(e) => dispatch({ set: { amount: clamp(Number(e.target.value), MAX_AMOUNT) } })}
              className="w-full accent-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
            />
            <div className="relative h-8" aria-hidden="true">
              <div
                className="absolute top-0 flex -translate-x-1/2 flex-col items-center text-xs font-semibold text-warning"
                style={{ left: `${limitPct}%` }}
              >
                <span>▲</span>
                <span className="whitespace-nowrap">
                  {t("risk.pg.limit")}: {fmtInt(String(limit), lang)}
                </span>
              </div>
            </div>
            <label htmlFor="pg-amount-num" className="sr-only">
              {t("risk.pg.amountNum")}
            </label>
            <input
              id="pg-amount-num"
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_AMOUNT}
              step={100}
              value={facts.amount}
              onChange={(e) => dispatch({ set: { amount: clamp(Number(e.target.value), MAX_AMOUNT) } })}
              className="w-40 rounded-xl border border-line bg-surface px-3 py-2 text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="pg-fraud-range" className="block text-sm font-semibold text-ink">
              {t("risk.pg.fraud")}
            </label>
            <input
              id="pg-fraud-range"
              type="range"
              min={0}
              max={100}
              step={1}
              value={facts.fraud_score}
              onChange={(e) => dispatch({ set: { fraud_score: clamp(Number(e.target.value), 100) } })}
              className="w-full accent-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
            />
            <label htmlFor="pg-fraud-num" className="sr-only">
              {t("risk.pg.fraudNum")}
            </label>
            <input
              id="pg-fraud-num"
              type="number"
              inputMode="numeric"
              min={0}
              max={100}
              value={facts.fraud_score}
              onChange={(e) => dispatch({ set: { fraud_score: clamp(Number(e.target.value), 100) } })}
              className="w-24 rounded-xl border border-line bg-surface px-3 py-2 text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            />
          </div>

          <ul className="space-y-2">
            {TOGGLES.map((x) => (
              <li key={x.key}>
                <label className="flex cursor-pointer items-center gap-3 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={facts[x.key]}
                    onChange={(e) => dispatch({ set: { [x.key]: e.target.checked } })}
                    className="size-5 accent-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                  />
                  {t(x.label)}
                </label>
              </li>
            ))}
          </ul>
          <Button variant="secondary" onClick={() => dispatch({ reset: true })}>
            {t("risk.pg.reset")}
          </Button>
        </Card>

        <section aria-labelledby="pg-result-h" aria-live="polite" aria-busy={updating} className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 id="pg-result-h" className="text-lg font-bold text-ink">
              {t("risk.pg.result")}
            </h2>
            {updating ? <span className="text-sm text-muted">{t("risk.pg.updating")}</span> : null}
          </div>
          {result.error ? (
            <QueryError error={result.error} onRetry={result.reload} />
          ) : result.data ? (
            <RiskDecisionCard risk={result.data} showSimulated={false} />
          ) : (
            <Skeleton className="h-64" />
          )}
        </section>
      </div>
    </div>
  );
}
