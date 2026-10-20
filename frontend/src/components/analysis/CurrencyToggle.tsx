"use client";

import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useT } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";

type Props = { value: Currency; onChange: (c: Currency) => void };

export function CurrencyToggle({ value, onChange }: Props) {
  const t = useT();
  return (
    <SegmentedControl<Currency>
      legend={t("analysis.currency")}
      value={value}
      onChange={onChange}
      options={[
        { value: "USD", label: "USD", title: "US dollar" },
        { value: "BDT", label: "BDT", title: "Bangladeshi taka" },
        { value: "CNY", label: "CNY", title: "Chinese yuan" },
      ]}
    />
  );
}
