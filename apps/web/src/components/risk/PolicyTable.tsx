"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { useLang, useT } from "@/i18n";
import type { PolicyOut, RiskKind } from "@/lib/api/risk";
import { formatMoney } from "@/lib/format";

import { fmtInt, pick } from "./riskText";

type Props = { policy: PolicyOut };

const GROUPS: { kind: RiskKind; tone: "danger" | "warning"; icon: string }[] = [
  { kind: "BLOCK", tone: "danger", icon: "⛔" },
  { kind: "TIER3", tone: "danger", icon: "⚠" },
  { kind: "TIER2", tone: "warning", icon: "▲" },
];
const th = "px-3 py-2 text-left font-semibold";
const td = "px-3 py-2 align-top";

export function PolicyTable({ policy }: Props) {
  const t = useT();
  const { lang } = useLang();
  const [yaml, setYaml] = useState(false);
  const thresholds: [string, string][] = [
    [t("risk.policy.tier1Max"), formatMoney(policy.tier1_max_usd, "USD", lang)],
    [t("risk.policy.fraudAbove"), fmtInt(String(policy.fraud_score_tier3_above), lang)],
    [t("risk.policy.newDays"), fmtInt(String(policy.new_beneficiary_days), lang)],
    [t("risk.policy.cooling"), fmtInt(String(policy.cooling_off_minutes), lang)],
  ];
  return (
    <div className="space-y-4" data-testid="policy-table">
      <Card>
        <h3 className="mb-2 text-base font-bold text-ink">{t("risk.policy.thresholds")}</h3>
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {thresholds.map(([k, v]) => (
            <div key={k}>
              <dt className="text-sm text-muted">{k}</dt>
              <dd className="text-lg font-bold text-ink tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>
      {GROUPS.map((g) => {
        const rules = policy.rules.filter((r) => r.kind === g.kind);
        if (rules.length === 0) return null;
        return (
          <Card key={g.kind}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-144 text-sm">
                <caption className="mb-2 text-left">
                  <Badge tone={g.tone} icon={g.icon}>
                    {t(`risk.policy.group.${g.kind}`)}
                  </Badge>
                </caption>
                <thead>
                  <tr className="border-b border-line text-muted">
                    <th scope="col" className={th}>{t("risk.policy.rule")}</th>
                    <th scope="col" className={th}>{t("risk.policy.appliesTo")}</th>
                    <th scope="col" className={th}>{t("risk.policy.condition")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((r) => (
                    <tr key={r.code} className="border-b border-line last:border-0" data-testid="policy-rule">
                      <td className={td}>
                        <span className="font-semibold text-ink">{pick(lang, r.label_en, r.label_bn)}</span>
                        <span className="block font-mono text-xs text-muted">{r.code}</span>
                      </td>
                      <td className={td}>{r.applies_to.join(", ")}</td>
                      <td className={td}>{pick(lang, r.condition_en, r.condition_bn)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        );
      })}
      <div>
        <button
          type="button"
          aria-expanded={yaml}
          onClick={() => setYaml((v) => !v)}
          className="rounded-md text-sm font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {t(yaml ? "risk.policy.yamlHide" : "risk.policy.yaml")}
        </button>
        {yaml ? (
          <>
            <p className="mt-2 text-xs text-muted">{t("risk.policy.source", { source: policy.source })}</p>
            <pre
              tabIndex={0}
              className="mt-1 max-h-96 overflow-auto rounded-xl border border-line bg-surface-alt p-3 text-xs text-ink focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              {policy.yaml}
            </pre>
          </>
        ) : null}
      </div>
    </div>
  );
}
