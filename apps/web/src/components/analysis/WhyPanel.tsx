"use client";

import { Card } from "@/components/ui/Card";
import { pickLang, useLang, useT } from "@/i18n";
import type { Explanation } from "@/lib/api/analysis";

type Props = { explanations: Explanation[]; facts: string[] };

export function WhyPanel({ explanations, facts }: Props) {
  const t = useT();
  const { lang } = useLang();
  return (
    <Card as="section" labelledBy="why-h">
      <h2 id="why-h" className="text-lg font-semibold text-ink">
        {t("analysis.why.title")}
      </h2>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-ink">
        {explanations.map((e) => (
          <li key={e.code}>{pickLang(e, lang)}</li>
        ))}
      </ul>
      {facts.length > 0 ? (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer font-semibold text-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
            {t("analysis.why.facts")}
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
            {facts.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </Card>
  );
}
