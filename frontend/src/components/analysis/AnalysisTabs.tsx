"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Tabs } from "@/components/ui/Tabs";
import { useT } from "@/i18n";

import { LandedCostCalculator } from "./LandedCostCalculator";
import { MonthlySummary } from "./MonthlySummary";
import { SupplierScorecard } from "./SupplierScorecard";

const IDS = ["calculator", "monthly", "suppliers"] as const;
type TabId = (typeof IDS)[number];

export function AnalysisTabs() {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get("tab");
  const selected: TabId = IDS.find((i) => i === raw) ?? "calculator";

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-ink">{t("analysis.title")}</h1>
      <Tabs
        label={t("analysis.tabs")}
        selected={selected}
        onSelect={(id) =>
          router.replace(`${pathname}?tab=${id}`, { scroll: false })
        }
        tabs={[
          { id: "calculator", label: t("analysis.tab.calculator") },
          { id: "monthly", label: t("analysis.tab.monthly") },
          { id: "suppliers", label: t("analysis.tab.suppliers") },
        ]}
      >
        {selected === "calculator" ? <LandedCostCalculator /> : null}
        {selected === "monthly" ? <MonthlySummary /> : null}
        {selected === "suppliers" ? <SupplierScorecard /> : null}
      </Tabs>
    </div>
  );
}
