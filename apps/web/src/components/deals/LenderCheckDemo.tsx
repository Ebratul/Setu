"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import type { DealDetail } from "@/lib/api/deals";
import { listDocuments } from "@/lib/api/documents";
import { LENDER_B_ID, isDemoMode, isDuplicate, lenderCheck, type LenderCheck } from "@/lib/api/registry";
import { formatDate } from "@/lib/format";

type Outcome = { kind: "result"; check: LenderCheck } | { kind: "none" } | { kind: "error" };

/** Demo/judge helper: asks the shared registry whether "Lender B" could finance this deal's invoice. */
export function LenderCheckDemo({ deal }: { deal: DealDetail }) {
  const t = useT();
  const { lang } = useLang();
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  if (!isDemoMode(deal.viewer_role)) return null;

  async function run() {
    setBusy(true);
    setOutcome(null);
    try {
      const { documents } = await listDocuments(deal.id);
      const invoice =
        documents.find((d) => d.doc_type === "PROFORMA_INVOICE") ??
        documents.find((d) => d.doc_type === "COMMERCIAL_INVOICE");
      if (!invoice) {
        setOutcome({ kind: "none" });
        return;
      }
      setOutcome({ kind: "result", check: await lenderCheck(LENDER_B_ID, invoice.id) });
    } catch {
      setOutcome({ kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  const check = outcome?.kind === "result" ? outcome.check : null;
  const blocked = check ? isDuplicate(check.result) : false;
  const date = check?.registered_on ? formatDate(check.registered_on.slice(0, 10), lang) : "";
  const purpose = t(`reg.purposeLower.${check?.already_registered_for ?? "FINANCING_COLLATERAL"}`);

  return (
    <div data-testid="lender-check-demo">
    <Card as="section" labelledBy="lc-h" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="lc-h" className="text-base font-bold text-ink">
          {t("reg.demo.title")}
        </h2>
        <SimulatedBadge />
      </div>
      <p className="text-sm text-muted">{t("reg.demo.intro")}</p>
      <Button variant="secondary" onClick={run} disabled={busy} data-testid="lender-check-button">
        {busy ? t("reg.demo.busy") : t("reg.demo.button")}
      </Button>
      <div role="status" aria-live="polite">
        {blocked ? (
          <p data-testid="lender-check-blocked" className="rounded-xl border-2 border-danger bg-danger-soft p-3 text-sm font-semibold text-danger">
            <span aria-hidden="true">✕ </span>
            <strong>{t("reg.demo.blockedTitle")}. </strong>
            {check?.held_by
              ? t("reg.demo.blocked", { purpose, holder: check.held_by, date })
              : t("reg.demo.blockedNoHolder", { purpose, date })}
          </p>
        ) : check ? (
          <p data-testid="lender-check-clear" className="rounded-xl border border-success bg-success-soft p-3 text-sm font-semibold text-success">
            <span aria-hidden="true">✓ </span>
            <strong>{t("reg.demo.clearTitle")}. </strong>
            {t("reg.demo.clear")}
          </p>
        ) : outcome?.kind === "none" ? (
          <p className="text-sm text-muted">{t("reg.demo.noInvoice")}</p>
        ) : outcome?.kind === "error" ? (
          <p className="text-sm font-semibold text-danger">{t("reg.demo.error")}</p>
        ) : null}
      </div>
    </Card>
    </div>
  );
}
