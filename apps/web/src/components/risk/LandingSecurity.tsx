"use client";

import Link from "next/link";

import { useT } from "@/i18n";

/** Static summary (the policy endpoint needs a session); links to the interactive playground. */
export function LandingSecurity() {
  const t = useT();
  const rows = [
    { k: "t1", icon: "ℹ" },
    { k: "t2", icon: "▲" },
    { k: "t3", icon: "⚠" },
    { k: "block", icon: "⛔" },
  ] as const;
  return (
    <section aria-labelledby="land-sec-h" className="w-full space-y-3 rounded-card bg-surface p-6 shadow-card">
      <h2 id="land-sec-h" className="text-xl font-bold text-ink">
        {t("risk.land.title")}
      </h2>
      <p className="text-muted">{t("risk.land.intro")}</p>
      <ul className="space-y-2 text-sm text-ink">
        {rows.map((r) => (
          <li key={r.k} className="flex gap-2">
            <span aria-hidden="true">{r.icon}</span>
            <span>{t(`risk.land.${r.k}`)}</span>
          </li>
        ))}
      </ul>
      <Link
        href="/demo/risk-playground"
        className="inline-block font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        {t("risk.land.link")}
      </Link>
    </section>
  );
}
