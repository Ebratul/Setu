"use client";

import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { Icon, type IconName } from "@/components/ui/Icon";
import { TierBadge } from "@/components/ui/TierBadge";
import { useT } from "@/i18n";

import { Section } from "./Section";

export const LAYERS: { id: string; icon: IconName; href: string }[] = [
  { id: "risk", icon: "scale", href: "/demo/risk-playground" },
  { id: "approvals", icon: "lock", href: "/demo/scam-simulator" },
  { id: "privacy", icon: "eye", href: "/demo/privacy-playground" },
  { id: "injection", icon: "shield", href: "/demo/attack-console" },
  { id: "audit", icon: "check", href: "/verify" },
];

export function SecurityBand() {
  const t = useT();
  return (
    <Section id="security" title={t("landing.security.title")} lead={t("landing.security.lead")} alt>
      <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {LAYERS.map((l, i) => (
          <li key={l.id} className="min-w-0">
            <Card interactive className="flex h-full flex-col">
              <span className="flex items-center gap-2 text-sm font-bold text-brand-text">
                <span className="flex size-7 items-center justify-center rounded-full bg-brand-700 text-xs text-white">
                  {i + 1}
                </span>
                <Icon name={l.icon} size={18} />
              </span>
              <h3 className="mt-3 text-base font-bold text-ink">{t(`landing.security.${l.id}.name`)}</h3>
              <p className="mt-2 flex-1 text-sm text-muted">{t(`landing.security.${l.id}.desc`)}</p>
              <Link
                href={l.href}
                aria-label={t("landing.security.tryAria", { name: t(`landing.security.${l.id}.name`) })}
                className="mt-4 inline-flex min-h-11 items-center gap-1 self-start rounded-lg font-semibold text-brand-text hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                {t("landing.security.try")}
                <Icon name="arrow" size={16} className="rtl:rotate-180" />
              </Link>
            </Card>
          </li>
        ))}
      </ol>
      <div className="mt-8 rounded-card border border-line bg-surface p-5">
        <h3 className="text-base font-bold text-ink">{t("landing.security.tiersTitle")}</h3>
        <p className="mt-1 text-sm text-muted">{t("landing.security.tiersLead")}</p>
        <ul className="mt-4 flex flex-wrap gap-3">
          {[0, 1, 2, 3].map((tier) => (
            <li key={tier}>
              <TierBadge tier={tier} />
            </li>
          ))}
          <li>
            <TierBadge tier={3} decision="BLOCK" />
          </li>
        </ul>
      </div>
    </Section>
  );
}
