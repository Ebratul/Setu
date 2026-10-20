"use client";

import { Card } from "@/components/ui/Card";
import { useT } from "@/i18n";

import { Section } from "./Section";

const STATS = ["s1", "s2", "s3"] as const;

export function Problem() {
  const t = useT();
  return (
    <Section id="problem" title={t("landing.problem.title")} lead={t("landing.problem.lead")}>
      <ul className="grid gap-4 md:grid-cols-3">
        {STATS.map((s) => (
          <li key={s} className="min-w-0">
            <Card className="h-full">
              <p className="text-3xl font-extrabold break-words text-brand-text">
                {t(`landing.problem.${s}.value`)}
              </p>
              <p className="mt-2 text-base font-semibold text-ink">{t(`landing.problem.${s}.label`)}</p>
              <p className="mt-3 text-xs text-muted">{t(`landing.problem.${s}.source`)}</p>
            </Card>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs text-muted">{t("landing.problem.note")}</p>
    </Section>
  );
}
