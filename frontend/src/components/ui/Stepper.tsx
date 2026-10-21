import { Icon } from "./Icon";

export type Step = { id: string; label: string; hint?: string };

type Props = { steps: Step[]; current: number; label: string };

/** Horizontal progress steps; done = check icon, current = aria-current, never colour-only. */
export function Stepper({ steps, current, label }: Props) {
  return (
    <ol aria-label={label} className="flex flex-wrap gap-x-6 gap-y-3">
      {steps.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={s.id} aria-current={active ? "step" : undefined} className="flex items-center gap-2">
            <span
              className={`flex size-7 items-center justify-center rounded-full border text-xs font-bold ${
                done
                  ? "border-success bg-success-soft text-success"
                  : active
                    ? "border-brand-700 bg-brand-700 text-white"
                    : "border-line text-muted"
              }`}
            >
              {done ? <Icon name="check" size={14} /> : i + 1}
            </span>
            <span className={`text-sm ${active ? "font-semibold text-ink" : "text-muted"}`}>{s.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
