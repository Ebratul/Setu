"use client";

import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";

import { AuthShell } from "./AuthShell";

export const FALLBACK_TERMS_VERSION = "2026-10";
const CLAUSES = ["1", "2", "3", "4", "5", "6"] as const;

/** Plain-language sandbox terms or privacy notice; every clause is an i18n key `lgl.<kind>.c<n>`. */
export function LegalPage({ kind }: { kind: "terms" | "privacy" }) {
  const t = useT();
  return (
    <AuthShell title={t(`lgl.${kind}.title`)}>
      <article className="space-y-5 text-sm leading-relaxed text-ink">
        <div className="flex flex-wrap items-center gap-3">
          <SimulatedBadge />
          <p className="text-muted">
            {t("lgl.version", { version: FALLBACK_TERMS_VERSION })}
          </p>
        </div>
        <p
          role="note"
          className="rounded-xl border border-warning bg-warning-soft p-3"
        >
          {t("lgl.sandbox")}
        </p>
        <ol className="space-y-4">
          {CLAUSES.map((n) => (
            <li key={n}>
              <h2 className="font-bold">{t(`lgl.${kind}.h${n}`)}</h2>
              <p className="mt-1 text-muted">{t(`lgl.${kind}.c${n}`)}</p>
            </li>
          ))}
        </ol>
      </article>
    </AuthShell>
  );
}
