"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { KybBadge } from "@/components/kyb/KybBadge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { FormField, inputClass } from "@/components/ui/FormField";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useLang, useT } from "@/i18n";
import { postLandedCost, type LandedCostRequest, type OrderAnalysis } from "@/lib/api/analysis";
import { dealErrorText } from "@/lib/api/dealErrors";
import { createDeal } from "@/lib/api/deals";
import { getSuppliers, type SupplierListItem } from "@/lib/api/kyb";
import { formatMoney } from "@/lib/format";
import { useMoneyGate } from "@/lib/useAccountGate";
import { useApi, useDebounced } from "@/lib/useApi";

import {
  COST_KINDS,
  EMPTY_DRAFT,
  INCOTERMS,
  buildRequest,
  goodsErrors,
  goodsTotal,
  shipErrors,
  type Draft,
} from "./newDealModel";

const STEPS = ["supplier", "goods", "ship", "review"] as const;
type Step = (typeof STEPS)[number];

export function NewDealPage() {
  const t = useT();
  const gate = useMoneyGate();
  const { lang } = useLang();
  const router = useRouter();
  const toast = useToast();
  const suppliers = useApi((s) => getSuppliers(s), "new-deal-suppliers");
  const [step, setStep] = useState<Step>("supplier");
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [warn, setWarn] = useState<SupplierListItem | null>(null);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  const supplier = suppliers.data?.suppliers.find((s) => s.supplier_id === draft.supplierId);
  const total = goodsTotal(draft);
  const gErr = goodsErrors(draft);
  const sErr = shipErrors(draft);
  const goodsOk = Object.keys(gErr).length === 0 && total !== null;
  const shipOk = Object.keys(sErr).length === 0;
  const err = (k?: string) => (tried && k ? t(k) : null);

  const previewBody = useMemo(() => {
    if (!goodsOk || !shipOk || total === null) return null;
    const body: LandedCostRequest = {
      currency: draft.currency,
      goods_value: total,
      quantity: draft.quantity.trim(),
      unit: draft.unit.trim(),
      cost_lines: COST_KINDS.filter((k) => draft.costs[k].trim() !== "").map((k) => ({
        kind: k,
        amount: draft.costs[k].trim(),
      })),
    };
    // goods_value has at most 4 decimals in the API; longer exact products skip the preview.
    if (!/^\d{1,14}(\.\d{1,4})?$/.test(total)) return null;
    return JSON.stringify(body);
  }, [goodsOk, shipOk, total, draft]);
  const debounced = useDebounced(previewBody);
  const preview = useApi(
    (s) => postLandedCost(JSON.parse(debounced ?? "{}") as LandedCostRequest, s),
    `new-deal-preview|${debounced ?? ""}`,
    debounced !== null && (step === "ship" || step === "review"),
  );

  function pickSupplier(s: SupplierListItem) {
    if (s.kyb_badge === "WARNING" || s.kyb_badge === "BLOCKED") setWarn(s);
    else set("supplierId", s.supplier_id);
  }

  function next() {
    setTried(true);
    if (step === "supplier" && draft.supplierId) {
      setTried(false);
      setStep("goods");
    } else if (step === "goods" && goodsOk) {
      setTried(false);
      setStep("ship");
    } else if (step === "ship" && shipOk) {
      setTried(false);
      setStep("review");
    }
  }
  function back() {
    setTried(false);
    setError(null);
    setStep(STEPS[Math.max(0, STEPS.indexOf(step) - 1)]);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const deal = await createDeal(buildRequest(draft));
      toast(t("dn.created", { ref: deal.reference }), "success");
      router.push(`/app/deals/${encodeURIComponent(deal.reference)}`);
    } catch (e) {
      setError(dealErrorText(e, t));
      setBusy(false);
    }
  }

  const idx = STEPS.indexOf(step);
  const decimalProps = (key: keyof Draft, id: string, label: string, errKey?: string, hint?: string) => (
    <FormField id={id} label={label} error={err(errKey)} hint={hint}>
      {(aria) => (
        <input
          {...aria}
          type="text"
          inputMode="decimal"
          value={draft[key] as string}
          onChange={(e) => set(key, e.target.value as never)}
          className={inputClass}
        />
      )}
    </FormField>
  );
  const textField = (key: keyof Draft, id: string, label: string, errKey?: string) => (
    <FormField id={id} label={label} error={err(errKey)}>
      {(aria) => (
        <input
          {...aria}
          type="text"
          value={draft[key] as string}
          onChange={(e) => set(key, e.target.value as never)}
          className={inputClass}
        />
      )}
    </FormField>
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-ink">{t("dn.title")}</h1>
        <SimulatedBadge />
      </div>

      <ol aria-label={t("dn.steps")} className="flex flex-wrap gap-2 text-sm">
        {STEPS.map((s, i) => (
          <li
            key={s}
            aria-current={s === step ? "step" : undefined}
            className={`rounded-full border px-3 py-1 font-semibold ${
              s === step
                ? "border-brand-700 bg-brand-700 text-white"
                : i < idx
                  ? "border-success bg-success-soft text-success"
                  : "border-line bg-surface text-muted"
            }`}
          >
            <span aria-hidden="true">{i < idx ? "✓ " : `${i + 1}. `}</span>
            {t(`dn.step.${s}`)}
          </li>
        ))}
      </ol>

      <Card className="space-y-4">
        {step === "supplier" ? (
          suppliers.error ? (
            <QueryError error={suppliers.error} onRetry={suppliers.reload} />
          ) : !suppliers.data ? (
            <Skeleton className="h-32" />
          ) : (
            <fieldset className="space-y-2">
              <legend className="text-lg font-bold text-ink">{t("dn.pickSupplier")}</legend>
              {tried && !draft.supplierId ? (
                <p role="alert" className="text-sm font-medium text-danger">{t("dn.err.supplier")}</p>
              ) : null}
              <ul className="space-y-2">
                {suppliers.data.suppliers.map((s) => (
                  <li key={s.supplier_id}>
                    <label className="flex cursor-pointer flex-wrap items-center justify-between gap-2 rounded-xl border border-line p-3 has-checked:border-brand-700 has-checked:bg-brand-50 has-focus-visible:ring-2 has-focus-visible:ring-brand-500">
                      <span className="flex items-center gap-2">
                        <input
                          type="radio"
                          name="supplier"
                          checked={draft.supplierId === s.supplier_id}
                          onChange={() => pickSupplier(s)}
                        />
                        <span>
                          <span className="block font-semibold text-ink">{s.name}</span>
                          <span className="block text-xs text-muted">{s.city}, {s.country}</span>
                        </span>
                      </span>
                      <KybBadge status={s.kyb_badge} />
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          )
        ) : null}

        {step === "goods" ? (
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-ink">{t("dn.goodsTitle")}</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {textField("title", "dn-title", t("dn.goods"), gErr.title)}
              {textField("hsCode", "dn-hs", t("orders.hs"), gErr.hsCode)}
              {decimalProps("quantity", "dn-qty", t("orders.quantity"), gErr.quantity)}
              {textField("unit", "dn-unit", t("dn.unit"), gErr.unit)}
              {decimalProps("unitPrice", "dn-price", t("dn.unitPrice"), gErr.unitPrice)}
              <FormField id="dn-currency" label={t("calc.currency")}>
                {(aria) => (
                  <select
                    {...aria}
                    value={draft.currency}
                    onChange={(e) => set("currency", e.target.value as Draft["currency"])}
                    className={inputClass}
                  >
                    <option value="USD">USD</option>
                    <option value="CNY">CNY</option>
                  </select>
                )}
              </FormField>
              {decimalProps("expectedSale", "dn-sale", t("dn.expectedSale"), gErr.expectedSale, t("dn.optional"))}
            </div>
            <p aria-live="polite" data-testid="goods-total" className="rounded-xl bg-surface-alt p-3 text-sm text-ink">
              {t("dn.total")}:{" "}
              <strong className="tabular-nums">
                {total ? formatMoney(total, draft.currency, lang) : "—"}
              </strong>
              <span className="block text-xs text-muted">{t("dn.totalNote")}</span>
            </p>
          </div>
        ) : null}

        {step === "ship" ? (
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-ink">{t("dn.shipTitle")}</h2>
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField id="dn-incoterm" label={t("orders.incoterm")}>
                {(aria) => (
                  <select {...aria} value={draft.incoterm} onChange={(e) => set("incoterm", e.target.value)} className={inputClass}>
                    {INCOTERMS.map((i) => (
                      <option key={i} value={i}>{i}</option>
                    ))}
                  </select>
                )}
              </FormField>
              {textField("portOfLoading", "dn-pol", t("dn.pol"), sErr.portOfLoading)}
              {textField("portOfDischarge", "dn-pod", t("dn.pod"), sErr.portOfDischarge)}
            </div>
            <fieldset className="space-y-2">
              <legend className="font-semibold text-ink">{t("dn.extraCosts", { currency: draft.currency })}</legend>
              <div className="grid gap-4 sm:grid-cols-2">
                {COST_KINDS.map((k) => (
                  <FormField key={k} id={`dn-cost-${k}`} label={t(`kind.${k}`)} error={err(sErr[k])}>
                    {(aria) => (
                      <input
                        {...aria}
                        type="text"
                        inputMode="decimal"
                        value={draft.costs[k]}
                        onChange={(e) => set("costs", { ...draft.costs, [k]: e.target.value })}
                        className={inputClass}
                      />
                    )}
                  </FormField>
                ))}
              </div>
            </fieldset>
            <LandedPreview state={preview} />
          </div>
        ) : null}

        {step === "review" ? (
          <div className="space-y-4">
            <h2 className="text-lg font-bold text-ink">{t("dn.reviewTitle")}</h2>
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2" data-testid="review">
              {(
                [
                  [t("orders.supplier"), supplier?.name ?? "—"],
                  [t("dn.goods"), draft.title],
                  [t("orders.hs"), draft.hsCode],
                  [t("orders.quantity"), `${draft.quantity} ${draft.unit}`],
                  [t("dn.unitPrice"), formatMoney(draft.unitPrice, draft.currency, lang)],
                  [t("dn.total"), total ? formatMoney(total, draft.currency, lang) : "—"],
                  [t("orders.incoterm"), draft.incoterm],
                  [t("dd.route"), `${draft.portOfLoading} → ${draft.portOfDischarge}`],
                ] as [string, string][]
              ).map(([k, v]) => (
                <div key={k} className="min-w-0">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-semibold break-words text-ink">{v}</dd>
                </div>
              ))}
            </dl>
            <LandedPreview state={preview} />
            <p className="text-sm text-muted">{t("dn.draftNote")}</p>
            {error ? (
              <p role="alert" className="rounded-xl border border-danger bg-danger-soft p-3 text-sm font-medium text-danger">
                {error}
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="flex flex-wrap justify-between gap-2 border-t border-line pt-4">
          <Button variant="secondary" onClick={back} disabled={idx === 0 || busy}>
            {t("dn.back")}
          </Button>
          {step === "review" ? (
            <div className="min-w-0">
              <Button
                onClick={submit}
                disabled={busy || !gate.allowed}
                aria-describedby={gate.allowed ? undefined : "dn-create-why"}
              >
                {busy ? t("common.loading") : t("dn.create")}
              </Button>
              {gate.reason ? (
                <p
                  id="dn-create-why"
                  className="mt-1 max-w-xs text-xs text-muted"
                >
                  {gate.reason}
                </p>
              ) : null}
            </div>
          ) : (
            <Button onClick={next}>{t("dn.next")}</Button>
          )}
        </div>
      </Card>

      {warn ? (
        <ConfirmDialog
          title={t(warn.kyb_badge === "BLOCKED" ? "dn.blockedTitle" : "dn.warnTitle", { name: warn.name })}
          confirmLabel={t("dn.useAnyway")}
          onClose={() => setWarn(null)}
          onConfirm={() => {
            set("supplierId", warn.supplier_id);
            setWarn(null);
          }}
        >
          <p
            role={warn.kyb_badge === "BLOCKED" ? "alert" : undefined}
            className={warn.kyb_badge === "BLOCKED" ? "font-semibold text-danger" : undefined}
          >
            {t(warn.kyb_badge === "BLOCKED" ? "dn.blockedBody" : "dn.warnBody")}
          </p>
          <KybBadge status={warn.kyb_badge} />
        </ConfirmDialog>
      ) : null}
    </div>
  );
}

function LandedPreview({ state }: { state: { data?: OrderAnalysis; error?: unknown } }) {
  const t = useT();
  const { lang } = useLang();
  const c = state.data?.currency;
  return (
    <section aria-labelledby="lp-h" aria-live="polite" data-testid="landed-preview" className="rounded-xl border border-line bg-surface-alt p-3 text-sm">
      <h3 id="lp-h" className="font-semibold text-ink">{t("dn.landedTitle")}</h3>
      {state.error ? (
        <p className="text-muted">{t("dn.landedFail")}</p>
      ) : !state.data || !c ? (
        <p className="text-muted">{t("dn.landedWait")}</p>
      ) : (
        <p className="text-ink">
          {t("dn.landedTotal")}:{" "}
          <strong className="tabular-nums">{formatMoney(state.data.landed_cost[c], c, lang)}</strong>
          {" · "}
          {t("dn.landedUnit")}:{" "}
          <span className="tabular-nums">{formatMoney(state.data.cost_per_unit[c], c, lang)}</span>
          <span className="block text-xs text-muted">{t("dn.landedNote")}</span>
        </p>
      )}
    </section>
  );
}
