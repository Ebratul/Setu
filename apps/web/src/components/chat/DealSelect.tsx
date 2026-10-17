"use client";

import { useId } from "react";

import { inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { getOrders } from "@/lib/api/analysis";
import { useApi } from "@/lib/useApi";

type Props = { value: string | null; onChange: (v: string | null) => void };

export function DealSelect({ value, onChange }: Props) {
  const t = useT();
  const id = useId();
  const { data } = useApi(getOrders, "chat-deals");
  const orders = data?.orders ?? [];
  const match = orders.find((o) => o.reference === value || o.id === value);
  const selected = match?.reference ?? value ?? "";
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
      <label htmlFor={id} className="font-semibold text-ink">
        {t("chat.deal.label")}
      </label>
      <select
        id={id}
        value={selected}
        onChange={(e) => onChange(e.target.value || null)}
        className={`${inputClass} min-w-0 max-w-full flex-1 py-1.5`}
      >
        <option value="">{t("chat.deal.none")}</option>
        {!match && value ? <option value={value}>{value}</option> : null}
        {orders.map((o) => (
          <option key={o.id} value={o.reference}>
            {o.reference} · {o.title}
          </option>
        ))}
      </select>
    </div>
  );
}
