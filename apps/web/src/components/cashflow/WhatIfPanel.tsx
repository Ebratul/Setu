"use client";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useLang, useT } from "@/i18n";
import type { Flow, Forecast } from "@/lib/api/cashflow";
import { formatDate, formatMoney, type Currency } from "@/lib/format";

import type { WhatIfErrors, WhatIfField, WhatIfState } from "./whatIf";

type Props = {
  forecast: Forecast;
  state: WhatIfState;
  errors: WhatIfErrors;
  active: boolean;
  loading: boolean;
  onChange: (next: WhatIfState) => void;
  onReset: () => void;
};

export function WhatIfPanel({
  forecast,
  state,
  errors,
  active,
  loading,
  onChange,
  onReset,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const cur = forecast.currency as Currency;
  const items: Flow[] = forecast.daily.flatMap((d) => d.items);
  const outgoing = items.filter((i) => i.direction === "OUT");
  const describe = (i: Flow) =>
    `${i.label} · ${formatDate(i.on, lang)} · ${formatMoney(i.amount, cur, lang)}`;
  const err = (f: WhatIfField) =>
    errors[f] ? t(`whatif.err.${errors[f]}`) : null;
  const set = (patch: Partial<WhatIfState>) => onChange({ ...state, ...patch });

  function toggleRemoved(ref: string) {
    set({
      removed: state.removed.includes(ref)
        ? state.removed.filter((r) => r !== ref)
        : [...state.removed, ref],
    });
  }

  return (
    <Card as="section" labelledBy="whatif-h" className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="whatif-h" className="text-lg font-semibold text-ink">
          {t("whatif.title")}
        </h3>
        <div className="flex items-center gap-2">
          {active ? (
            <Badge tone="info" icon="◐">
              {t("whatif.badge")}
            </Badge>
          ) : null}
          <Button variant="secondary" onClick={onReset}>
            {t("whatif.reset")}
          </Button>
        </div>
      </div>
      <p className="text-sm text-muted">{t("whatif.intro")}</p>

      <fieldset className="space-y-3">
        <legend className="font-semibold text-ink">
          {t("whatif.move.title")}
        </legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id="wi-move-ref" label={t("whatif.move.item")}>
            {(aria) => (
              <select
                {...aria}
                value={state.moveRef}
                onChange={(e) => set({ moveRef: e.target.value, moveOn: "" })}
                className={inputClass}
              >
                <option value="">{t("whatif.move.none")}</option>
                {outgoing.map((i) => (
                  <option key={i.ref} value={i.ref}>
                    {describe(i)}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField
            id="wi-move-on"
            label={t("whatif.move.date")}
            error={err("moveOn")}
          >
            {(aria) => (
              <input
                {...aria}
                type="date"
                value={state.moveOn}
                min={forecast.start}
                max={forecast.end}
                disabled={!state.moveRef}
                onChange={(e) => set({ moveOn: e.target.value })}
                className={inputClass}
              />
            )}
          </FormField>
        </div>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="font-semibold text-ink">
          {t("whatif.loan.title")}
        </legend>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={state.loanOn}
            onChange={(e) => set({ loanOn: e.target.checked })}
            className="size-4 accent-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
          />
          {t("whatif.loan.enable")}
        </label>
        {state.loanOn ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField
              id="wi-loan-amount"
              label={t("whatif.loan.amount", { currency: forecast.currency })}
              hint={t("whatif.loan.amountHint", {
                amount: formatMoney(forecast.cover_amount, cur, lang),
              })}
              error={err("loanAmount")}
            >
              {(aria) => (
                <input
                  {...aria}
                  inputMode="decimal"
                  value={state.loanAmount}
                  onChange={(e) => set({ loanAmount: e.target.value.trim() })}
                  className={inputClass}
                />
              )}
            </FormField>
            <FormField
              id="wi-loan-date"
              label={t("whatif.loan.date")}
              error={err("loanDate")}
            >
              {(aria) => (
                <input
                  {...aria}
                  type="date"
                  value={state.loanDate}
                  min={forecast.start}
                  max={forecast.end}
                  onChange={(e) => set({ loanDate: e.target.value })}
                  className={inputClass}
                />
              )}
            </FormField>
            <FormField
              id="wi-repay-date"
              label={t("whatif.loan.repayDate")}
              error={err("repayDate")}
            >
              {(aria) => (
                <input
                  {...aria}
                  type="date"
                  value={state.repayDate}
                  min={forecast.start}
                  max={forecast.end}
                  onChange={(e) => set({ repayDate: e.target.value })}
                  className={inputClass}
                />
              )}
            </FormField>
            <FormField
              id="wi-repay-amount"
              label={t("whatif.loan.repayAmount", {
                currency: forecast.currency,
              })}
              error={err("repayAmount")}
            >
              {(aria) => (
                <input
                  {...aria}
                  inputMode="decimal"
                  value={state.repayAmount}
                  onChange={(e) => set({ repayAmount: e.target.value.trim() })}
                  className={inputClass}
                />
              )}
            </FormField>
          </div>
        ) : null}
      </fieldset>

      <fieldset>
        <legend className="font-semibold text-ink">
          {t("whatif.remove.title")}
        </legend>
        <p className="mt-1 text-xs text-muted">{t("whatif.remove.hint")}</p>
        <ul className="mt-2 max-h-64 space-y-1 overflow-y-auto rounded-xl border border-line p-2">
          {items.map((i) => (
            <li key={i.ref}>
              <label className="flex items-start gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={state.removed.includes(i.ref)}
                  onChange={() => toggleRemoved(i.ref)}
                  className="mt-0.5 size-4 shrink-0 accent-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
                />
                <span>
                  <span aria-hidden="true">
                    {i.direction === "IN" ? "↓ " : "↑ "}
                  </span>
                  <span className="sr-only">{t(`cf.dir.${i.direction}`)} </span>
                  {describe(i)}
                </span>
              </label>
            </li>
          ))}
        </ul>
      </fieldset>
      <p role="status" className="text-xs text-muted">
        {loading ? t("common.updating") : ""}
      </p>
    </Card>
  );
}
