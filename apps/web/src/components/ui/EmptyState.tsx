import type { ReactNode } from "react";

type Props = { title: string; body?: string; action?: ReactNode };

export function EmptyState({ title, body, action }: Props) {
  return (
    <div className="rounded-card border border-dashed border-line bg-surface p-8 text-center">
      <p className="font-semibold text-ink">{title}</p>
      {body ? <p className="mt-1 text-sm text-muted">{body}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
