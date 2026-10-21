"use client";

import type { ReactNode } from "react";

import { Icon, type IconName } from "@/components/ui/Icon";
import { useT } from "@/i18n";

type Kind = "info" | "tip" | "warning" | "security";

const STYLE: Record<Kind, { box: string; icon: IconName }> = {
  info: { box: "border-info bg-info-soft", icon: "info" },
  tip: { box: "border-success bg-success-soft", icon: "sparkle" },
  warning: { box: "border-warning bg-warning-soft", icon: "warn" },
  security: { box: "border-brand-500 bg-surface-alt", icon: "shield" },
};

type Props = { type?: Kind; title?: string; children: ReactNode };

export function Callout({ type = "info", title, children }: Props) {
  const t = useT();
  const s = STYLE[type] ?? STYLE.info;
  return (
    <aside className={`not-prose my-4 flex gap-3 rounded-card border p-4 ${s.box}`}>
      <Icon name={s.icon} size={20} className="mt-1 shrink-0 text-ink" />
      <div className="min-w-0 space-y-1 text-[0.9375rem] text-ink">
        <p className="font-semibold">{title ?? t(`docs.callout.${type}`)}</p>
        <div className="space-y-2 [&>p]:m-0">{children}</div>
      </div>
    </aside>
  );
}
