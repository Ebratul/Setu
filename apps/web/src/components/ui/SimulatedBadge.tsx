"use client";

import { useT } from "@/i18n";

export function SimulatedBadge() {
  const t = useT();
  return (
    <span
      title={t("common.simulatedHint")}
      className="inline-flex items-center rounded-full border border-warning bg-warning-soft px-3 py-1 text-xs font-semibold tracking-wide text-warning uppercase"
    >
      {t("common.simulated")}
    </span>
  );
}
