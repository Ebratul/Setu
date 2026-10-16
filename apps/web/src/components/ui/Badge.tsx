import type { ReactNode } from "react";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info";

export const toneClasses: Record<Tone, string> = {
  neutral: "border-line bg-surface-alt text-ink",
  success: "border-success bg-success-soft text-success",
  warning: "border-warning bg-warning-soft text-warning",
  danger: "border-danger bg-danger-soft text-danger",
  info: "border-info bg-info-soft text-info",
};

type Props = { tone?: Tone; icon?: ReactNode; children: ReactNode };

export function Badge({ tone = "neutral", icon, children }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${toneClasses[tone]}`}
    >
      {icon ? <span aria-hidden="true">{icon}</span> : null}
      {children}
    </span>
  );
}
