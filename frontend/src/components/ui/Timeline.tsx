import type { ReactNode } from "react";

import { Icon } from "./Icon";
import { toneClasses, toneIcons, type Tone } from "./Badge";

export type TimelineItem = { id: string; title: ReactNode; when?: string; body?: ReactNode; tone?: Tone };

export function Timeline({ items, label }: { items: TimelineItem[]; label: string }) {
  return (
    <ol aria-label={label} className="space-y-4">
      {items.map((it) => {
        const tone = it.tone ?? "neutral";
        return (
          <li key={it.id} className="flex gap-3">
            <span className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border ${toneClasses[tone]}`}>
              <Icon name={toneIcons[tone]} size={14} />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">{it.title}</p>
              {it.when ? <p className="text-xs text-muted">{it.when}</p> : null}
              {it.body ? <div className="mt-1 text-sm text-muted">{it.body}</div> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
