"use client";

import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useT } from "@/i18n";

import { Section } from "./Section";

export const FEATURES: { id: string; icon: IconName }[] = [
  { id: "financing", icon: "coins" },
  { id: "cashflow", icon: "trend" },
  { id: "analysis", icon: "chart" },
  { id: "forensics", icon: "file" },
  { id: "risk", icon: "shield" },
  { id: "cny", icon: "swap" },
  { id: "chat", icon: "chat" },
];

export function Features() {
  const t = useT();
  return (
    <Section id="features" title={t("landing.features.title")} lead={t("landing.features.lead")}>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f, i) => (
          <li key={f.id} className="min-w-0">
            <Card interactive className="flex h-full flex-col">
              <span className="flex size-11 items-center justify-center rounded-xl bg-brand-50 text-brand-text">
                <Icon name={f.icon} size={22} />
              </span>
              <h3 className="mt-4 text-lg font-bold text-ink">{t(`landing.features.${f.id}.name`)}</h3>
              <p className="mt-2 flex-1 text-sm text-muted">{t(`landing.features.${f.id}.desc`)}</p>
              <Link
                href={`/demo?step=${i + 1}`}
                aria-label={t("landing.features.seeItAria", { name: t(`landing.features.${f.id}.name`) })}
                className="mt-4 inline-flex min-h-11 items-center gap-1 self-start rounded-lg font-semibold text-brand-text hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                {t("landing.features.seeIt")}
                <Icon name="arrow" size={16} className="rtl:rotate-180" />
              </Link>
            </Card>
          </li>
        ))}
      </ul>
    </Section>
  );
}
