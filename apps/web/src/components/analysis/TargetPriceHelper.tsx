"use client";

import { Card } from "@/components/ui/Card";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import type { Currency, OrderAnalysis } from "@/lib/api/analysis";

import { Money } from "./Money";

type Props = {
  data: OrderAnalysis;
  currency: Currency;
  value: string;
  error: string | null;
  updating: boolean;
  onChange: (v: string) => void;
};

export function TargetPriceHelper({
  data,
  currency,
  value,
  error,
  updating,
  onChange,
}: Props) {
  const t = useT();
  return (
    <Card as="section" labelledBy="target-h">
      <h2 id="target-h" className="text-lg font-semibold text-ink">
        {t("analysis.target.title")}
      </h2>
      <dl className="mt-3 text-sm">
        <dt className="text-muted">{t("analysis.target.breakEven")}</dt>
        <dd className="text-xl font-bold text-ink">
          <Money amounts={data.break_even_price_per_unit} currency={currency} />
          <span className="ml-1 text-sm font-normal text-muted">
            / {data.unit}
          </span>
        </dd>
      </dl>
      <div className="mt-4 max-w-48">
        <FormField
          id="target-margin"
          label={t("analysis.target.input")}
          error={error}
          hint={t("analysis.target.hint")}
        >
          {(aria) => (
            <input
              {...aria}
              type="text"
              inputMode="decimal"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              className={inputClass}
            />
          )}
        </FormField>
      </div>
      <div aria-live="polite" className="mt-3 text-sm">
        {updating ? (
          <p className="text-muted">{t("common.updating")}</p>
        ) : data.target ? (
          <p className="text-ink">
            {t("analysis.target.result", { pct: data.target.margin_pct })}{" "}
            <strong className="text-lg">
              <Money amounts={data.target.price_per_unit} currency={currency} />
            </strong>{" "}
            / {data.unit}
          </p>
        ) : null}
      </div>
    </Card>
  );
}
