"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useToast } from "@/components/ui/Toast";
import { useT } from "@/i18n";
import { requestAccountChange, type AccountChangeIn } from "@/lib/api/approvals";
import { dealErrorText } from "@/lib/api/dealErrors";
import { listDeals } from "@/lib/api/deals";
import { useApi } from "@/lib/useApi";

import { Bi, useBi } from "./Bi";

type Props = { dealId: string; onSent: () => void };
type Fields = Omit<AccountChangeIn, "deal_id">;
type Errors = Partial<Record<keyof AccountChangeIn, string>>;

const EMPTY: Fields = {
  bank_name: "",
  bank_country: "",
  account_number: "",
  holder_name: "",
  account_type: "CORPORATE",
  currency: "USD",
};

export function ChangeAccountForm({ dealId, onSent }: Props) {
  const t = useT();
  const bi = useBi();
  const toast = useToast();
  const deals = useApi((s) => listDeals(undefined, s), "sp-deals");
  const [deal, setDeal] = useState(dealId);
  const [f, setF] = useState<Fields>(EMPTY);
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof Fields>(k: K, v: Fields[K]) => setF((p) => ({ ...p, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const required = t("chg.required");
    const errs: Errors = {};
    if (f.bank_name.trim().length < 2) errs.bank_name = required;
    if (!/^[A-Za-z]{2}$/.test(f.bank_country.trim())) errs.bank_country = required;
    if (!/^[A-Za-z0-9][A-Za-z0-9 -]{5,33}$/.test(f.account_number.trim())) errs.account_number = required;
    if (f.holder_name.trim().length < 2) errs.holder_name = required;
    setErrors(errs);
    setFormError(null);
    if (Object.keys(errs).length > 0) return;
    setBusy(true);
    try {
      await requestAccountChange({
        ...f,
        deal_id: deal,
        bank_name: f.bank_name.trim(),
        bank_country: f.bank_country.trim().toUpperCase(),
        account_number: f.account_number.trim(),
        holder_name: f.holder_name.trim(),
      });
      toast(t("chg.sent"), "success");
      setF(EMPTY);
      onSent();
    } catch (err) {
      setFormError(dealErrorText(err, t));
    }
    setBusy(false);
  }

  return (
    <Card as="section" labelledBy="chg-h" className="space-y-3">
      <h2 id="chg-h" className="text-lg font-bold text-ink">
        <Bi k="chg.title" />
      </h2>
      <p className="text-sm text-muted">{t("chg.intro")}</p>
      <form onSubmit={submit} noValidate className="grid gap-3 sm:grid-cols-2" data-testid="change-account-form">
        <FormField id="chg-deal" label={bi("chg.deal")}>
          {(a) => (
            <select {...a} value={deal} onChange={(e) => setDeal(e.target.value)} className={inputClass}>
              {(deals.data?.deals ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.reference}
                </option>
              ))}
              {!(deals.data?.deals ?? []).some((d) => d.id === dealId) ? <option value={dealId}>{dealId}</option> : null}
            </select>
          )}
        </FormField>
        <FormField id="chg-bank" label={bi("chg.bankName")} error={errors.bank_name}>
          {(a) => (
            <input {...a} required value={f.bank_name} onChange={(e) => set("bank_name", e.target.value)} className={inputClass} />
          )}
        </FormField>
        <FormField id="chg-country" label={bi("chg.country")} error={errors.bank_country}>
          {(a) => (
            <input {...a} required maxLength={2} value={f.bank_country} onChange={(e) => set("bank_country", e.target.value)} className={inputClass} />
          )}
        </FormField>
        <FormField id="chg-number" label={bi("chg.number")} error={errors.account_number}>
          {(a) => (
            <input {...a} required autoComplete="off" value={f.account_number} onChange={(e) => set("account_number", e.target.value)} className={inputClass} />
          )}
        </FormField>
        <FormField id="chg-holder" label={bi("chg.holder")} error={errors.holder_name}>
          {(a) => (
            <input {...a} required value={f.holder_name} onChange={(e) => set("holder_name", e.target.value)} className={inputClass} />
          )}
        </FormField>
        <FormField id="chg-type" label={bi("chg.type")}>
          {(a) => (
            <select {...a} value={f.account_type} onChange={(e) => set("account_type", e.target.value as Fields["account_type"])} className={inputClass}>
              <option value="CORPORATE">{bi("chg.CORPORATE")}</option>
              <option value="PERSONAL">{bi("chg.PERSONAL")}</option>
            </select>
          )}
        </FormField>
        <FormField id="chg-cur" label={bi("chg.currency")}>
          {(a) => (
            <select {...a} value={f.currency} onChange={(e) => set("currency", e.target.value as Fields["currency"])} className={inputClass}>
              <option value="USD">USD</option>
              <option value="CNY">CNY</option>
              <option value="BDT">BDT</option>
            </select>
          )}
        </FormField>
        <div className="flex items-end">
          <Button type="submit" disabled={busy} data-testid="submit-change">
            {busy ? bi("chg.submitting") : bi("chg.submit")}
          </Button>
        </div>
        {formError ? (
          <p role="alert" className="rounded-xl border border-danger bg-danger-soft p-3 text-sm font-medium text-danger sm:col-span-2">
            {formError}
          </p>
        ) : null}
      </form>
    </Card>
  );
}
