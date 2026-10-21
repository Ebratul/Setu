import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info";

export const toneClasses: Record<Tone, string> = {
  neutral: "border-line bg-surface-alt text-ink",
  success: "border-success bg-success-soft text-success",
  warning: "border-warning bg-warning-soft text-warning",
  danger: "border-danger bg-danger-soft text-danger",
  info: "border-info bg-info-soft text-info",
};

export const toneIcons: Record<Tone, IconName> = {
  neutral: "circle",
  success: "check",
  warning: "warn",
  danger: "ban",
  info: "info",
};

type Props = { tone?: Tone; icon?: ReactNode; children: ReactNode };

/** Always renders an icon next to the text so status is never colour-only. */
export function Badge({ tone = "neutral", icon, children }: Props) {
  return (
    <span
      data-tone={tone}
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${toneClasses[tone]}`}
    >
      <span aria-hidden="true" className="inline-flex">
        {icon ?? <Icon name={toneIcons[tone]} size={12} />}
      </span>
      {children}
    </span>
  );
}
