"use client";

import Link from "next/link";
import { useState } from "react";

import { pickLang } from "@/components/approvals/approvalText";
import { EmailBlockCard } from "@/components/inbox/EmailBlockCard";
import { TierBadge } from "@/components/risk/TierBadge";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import { simulate, notifyApprovalsChanged, type SimScenario, type SimulateResult } from "@/lib/api/approvals";
import { dealErrorText } from "@/lib/api/dealErrors";
import { useApi } from "@/lib/useApi";

const BUTTONS: { scenario: SimScenario; label: string }[] = [
  { scenario: "redirect-email", label: "sim.redirect" },
  { scenario: "supplier-account-change", label: "sim.account" },
  { scenario: "large-advance", label: "sim.large" },
];
const linkCls =
  "font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function ScamSimulatorPage() {
  const t = useT();
  const { lang } = useLang();
  const me = useApi((s) => getMe(s), "me");
  const [busy, setBusy] = useState<SimScenario | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulateResult | null>(null);

  async function run(s: SimScenario) {
    setBusy(s);
    setError(null);
    try {
      setResult(await simulate(s));
      notifyApprovalsChanged();
    } catch (e) {
      setError(dealErrorText(e, t));
    }
    setBusy(null);
  }

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("sim.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="max-w-3xl text-muted">{t("sim.intro")}</p>
        <p className="text-sm text-muted">{t("sim.dryRunNote")}</p>
        {me.data?.role === "JUDGE" ? <p className="text-sm font-semibold text-ink">{t("sim.judgeNote")}</p> : null}
      </header>
      <div className="flex flex-wrap gap-2">
        {BUTTONS.map((b) => (
          <Button key={b.scenario} onClick={() => run(b.scenario)} disabled={busy !== null} data-testid={`sim-${b.scenario}`}>
            {busy === b.scenario ? t("sim.running") : t(b.label)}
          </Button>
        ))}
      </div>
      {error ? (
        <p role="alert" className="rounded-xl border border-danger bg-danger-soft p-3 text-sm font-medium text-danger">
          {error}
        </p>
      ) : null}
      <div aria-live="polite">
        {result ? (
          <Card as="section" labelledBy="sim-res-h" className="space-y-4">
            <div data-testid="sim-result" data-scenario={result.scenario} className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <h2 id="sim-res-h" className="text-lg font-bold text-ink">
                  {pickLang(lang, result.title_en, result.title_bn)}
                </h2>
                {result.tier != null ? <TierBadge tier={result.tier} decision={result.outcome === "BLOCK" || result.outcome === "BLOCKED" ? "BLOCK" : undefined} /> : null}
                <Badge tone="info">
                  {t("sim.outcome")}: {result.outcome}
                </Badge>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="text-sm font-bold text-ink">{t("sim.did")}</h3>
                  <p className="text-sm text-ink">{pickLang(lang, result.what_we_did_en, result.what_we_did_bn)}</p>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-ink">{t("sim.responded")}</h3>
                  <p className="text-sm text-ink">{pickLang(lang, result.how_setu_responded_en, result.how_setu_responded_bn)}</p>
                </div>
              </div>
              {result.reasons.length > 0 ? (
                <div>
                  <h3 className="text-sm font-bold text-ink">{t("sim.reasons")}</h3>
                  <ul className="mt-1 flex flex-wrap gap-2">
                    {result.reasons.map((r) => (
                      <li key={r}>
                        <Badge tone="warning" icon="▲">
                          {r}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div className="flex flex-wrap gap-4 text-sm">
                {result.approval_id ? (
                  <Link href={`/app/approvals?focus=${result.approval_id}`} className={linkCls}>
                    {t("sim.openApproval")}
                  </Link>
                ) : null}
                {result.email ? (
                  <Link href="/app/inbox/email-check" className={linkCls}>
                    {t("sim.openInbox")}
                  </Link>
                ) : null}
              </div>
            </div>
            {result.email ? (
              <div className="space-y-2">
                <h3 className="text-sm font-bold text-ink">{t("sim.emailCard")}</h3>
                <EmailBlockCard email={result.email} />
              </div>
            ) : null}
          </Card>
        ) : null}
      </div>
    </div>
  );
}
