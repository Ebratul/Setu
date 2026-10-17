"use client";

import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { getOrders } from "@/lib/api/analysis";
import { useApi } from "@/lib/useApi";

type Props = { value: string | undefined; onChange: (ref: string) => void };

export function DealPicker({ value, onChange }: Props) {
  const t = useT();
  const { data } = useApi(getOrders, "fin-orders");
  const orders = data?.orders ?? [];
  return (
    <FormField id="fin-deal" label={t("fin.deal.label")}>
      {(aria) => (
        <select
          {...aria}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className={`${inputClass} max-w-xs`}
        >
          <option value="">{t("fin.deal.choose")}</option>
          {orders.map((o) => (
            <option key={o.reference} value={o.reference}>
              {o.reference} · {o.title}
            </option>
          ))}
        </select>
      )}
    </FormField>
  );
}
