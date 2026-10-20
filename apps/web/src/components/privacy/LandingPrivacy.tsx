"use client";

import Link from "next/link";

import { useT } from "@/i18n";

import { typeLabel } from "./privacyText";

// fictional values only
const ROWS = [
  { type: "PHONE", before: "+8801700-000123", after: "⟦PHONE_1⟧", icon: "☎" },
  { type: "ACCT", before: "6222 0000 1234 5678", after: "⟦ACCT_1⟧", icon: "#" },
  { type: "NID", before: "1990 000 123 456", after: "⟦NID_1⟧", icon: "🪪" },
] as const;

export function LandingPrivacy() {
  const t = useT();
  return (
    <section aria-labelledby="land-priv-h" className="w-full space-y-3 rounded-card bg-surface p-6 shadow-card">
      <h2 id="land-priv-h" className="text-xl font-bold text-ink">
        {t("privacy.land.title")}
      </h2>
      <p className="text-muted">{t("privacy.land.line")}</p>
      <table className="w-full text-sm text-ink">
        <thead className="sr-only">
          <tr>
            <th scope="col">{typeLabel(t, "ACCT", 1)}</th>
            <th scope="col">{t("privacy.land.before")}</th>
            <th scope="col">{t("privacy.land.after")}</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r, i) => (
            <tr key={r.type} className="border-b border-line last:border-0">
              <th scope="row" className="py-2 pr-2 text-left font-semibold whitespace-nowrap">
                <span aria-hidden="true">{r.icon} </span>
                {typeLabel(t, r.type, 1)}
              </th>
              <td className="py-2 pr-2 font-mono">
                <span className="priv-before inline-block" style={{ animationDelay: `${i * 0.4}s` }}>
                  {r.before}
                </span>
              </td>
              <td className="py-2 font-mono">
                <span aria-hidden="true">→ </span>
                <span
                  className="priv-after inline-block rounded-sm bg-brand-50 px-1 font-semibold text-brand-text"
                  style={{ animationDelay: `${i * 0.4}s` }}
                >
                  {r.after}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Link
        href="/demo/privacy-playground"
        className="inline-block rounded-md font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        {t("privacy.land.link")}
      </Link>
    </section>
  );
}
