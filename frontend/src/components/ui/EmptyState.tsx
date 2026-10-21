import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

type Props = { title: string; body?: string; action?: ReactNode; icon?: IconName };

export function EmptyState({ title, body, action, icon = "box" }: Props) {
  return (
    <div className="rounded-card border border-dashed border-line bg-surface p-8 text-center">
      <span className="mx-auto mb-3 flex size-11 items-center justify-center rounded-full bg-brand-50 text-brand-text">
        <Icon name={icon} size={22} />
      </span>
      <p className="font-semibold text-ink">{title}</p>
      {body ? <p className="mx-auto mt-1 max-w-md text-sm text-muted">{body}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
