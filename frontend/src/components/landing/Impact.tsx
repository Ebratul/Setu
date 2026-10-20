"use client";

import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";

import { Section } from "./Section";

const SIDES = ["exporter", "sme"] as const;
const ITEMS = ["i1", "i2", "i3"] as const;

export function Impact() {
  const t = useT();
  return (
    <Section id="impact" title={t("landing.impact.title")} lead={t("landing.impact.lead")}>
      <div className="grid gap-4 md:grid-cols-2">
        {SIDES.map((s) => (
          <Card key={s} as="article" labelledBy={`impact-${s}`} className="min-w-0">
            <h3 id={`impact-${s}`} className="text-lg font-bold text-ink">
              {t(`landing.impact.${s}.title`)}
            </h3>
            <ul className="mt-4 grid gap-3">
              {ITEMS.map((i) => (
                <li key={i} className="flex items-start gap-3 text-sm text-ink">
                  <Icon name="check" size={18} className="mt-0.5 shrink-0 text-success" />
                  <span className="min-w-0">{t(`landing.impact.${s}.${i}`)}</span>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </Section>
  );
}
