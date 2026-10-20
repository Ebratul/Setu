import type { ReactNode } from "react";

import { Icon } from "./Icon";
import { toneClasses, toneIcons, type Tone } from "./Badge";

type Props = {
  tone?: Tone;
  title?: string;
  children?: ReactNode;
  action?: ReactNode;
  /** `alert` interrupts (Tier 3 freezes); default is a polite status. */
  urgent?: boolean;
};

export function Alert({ tone = "info", title, children, action, urgent = false }: Props) {
  return (
    <div
      role={urgent ? "alert" : "status"}
      className={`flex items-start gap-3 rounded-card border p-4 ${toneClasses[tone]}`}
    >
      <Icon name={toneIcons[tone]} size={20} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1 text-sm">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className="text-ink">{children}</div> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
