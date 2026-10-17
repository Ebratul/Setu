"use client";

import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import type { Gap } from "@/lib/api/financing";
import { formatMoney, INPUT_DECIMAL } from "@/lib/format";
import { useLang } from "@/i18n";

type Props = {
  value: string;
  gap: Gap | undefined;
  onChange: (v: string) => void;
  onUseSuggested: () => void;
};

const ZERO = /^0+(\.0+)?$/;

export function isValidAmount(v: string) {
  return INPUT_DECIMAL.test(v) && !ZERO.test(v);
}

export function AmountControls({
  value,
  gap,
  onChange,
  onUseSuggested,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const invalid = value !== "" && !isValidAmount(value);
  const suggested = gap?.amount[gap.currency];
  const peak = gap?.peak_amount[gap.currency];
  const showPeak =
    gap !== undefined &&
    gap.mode === "shortfall" &&
    suggested !== undefined &&
    peak !== undefined &&
    Number(peak) > Number(suggested);
  return (
    <div className="space-y-2">
      <FormField
        id="fin-amount"
        label={`${t("fin.amount.label")}${gap ? ` (${gap.currency})` : ""}`}
        error={invalid ? t("fin.amount.invalid") : null}
        hint={t("fin.amount.hint")}
      >
        {(aria) => (
          <input
            {...aria}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={value}
            onChange={(e) => onChange(e.target.value.trim())}
            className={`${inputClass} max-w-xs`}
          />
        )}
      </FormField>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          disabled={!gap || gap.no_financing_needed}
          onClick={onUseSuggested}
        >
          {t("fin.amount.useSuggested")}
        </Button>
        {showPeak && gap && peak ? (
          <Button variant="secondary" onClick={() => onChange(peak)}>
            {t("fin.amount.coverPeak", {
              amount: formatMoney(peak, gap.currency, lang),
            })}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
