"use client";

import { Icon } from "@/components/ui/Icon";
import { useLang, useT } from "@/i18n";
import type { DemoStep, SceneResult } from "@/lib/api/demo";

import { biText, isDone, sceneKey, toDemoLang } from "./demoModel";
import { TAG_STYLE } from "./NarrationPanel";

type Props = {
  steps: DemoStep[];
  results: Record<string, SceneResult>;
  currentStep: number | null;
  disabled: boolean;
  onJump: (n: number) => void;
};

export function StepList({ steps, results, currentStep, disabled, onJump }: Props) {
  const t = useT();
  const lang = toDemoLang(useLang().lang);
  return (
    <nav aria-label={t("demo.steps.label")}>
      <ol className="space-y-1">
        {steps.map((s) => {
          const done = s.scenes.filter((sc) => isDone(results[sceneKey(s.n, sc.k)])).length;
          const failed = s.scenes.some((sc) => results[sceneKey(s.n, sc.k)]?.status === "failed");
          const complete = done === s.scenes.length;
          const current = s.n === currentStep;
          return (
            <li key={s.n}>
              <button
                type="button"
                disabled={disabled}
                aria-current={current ? "step" : undefined}
                onClick={() => onJump(s.n)}
                className={`flex min-h-11 w-full items-center gap-2 rounded-xl px-2.5 py-1.5 text-left text-sm focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none disabled:opacity-50 ${
                  current ? "bg-brand-50 font-bold text-ink ring-1 ring-brand-700" : "text-ink hover:bg-surface-alt"
                }`}
              >
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full border border-line bg-surface text-xs font-bold">{s.n}</span>
                <span className="min-w-0 flex-1 truncate">{biText(s.title, lang)}</span>
                <span className="flex shrink-0 items-center gap-1 text-xs text-muted">
                  <Icon name={TAG_STYLE[s.tag].icon} size={12} />
                  <span className="sr-only">{t(`demo.tag.${s.tag}`)}. </span>
                  {done}/{s.scenes.length}
                  {failed ? (
                    <Icon name="warn" size={12} className="text-warning" title={t("demo.steps.hadIssue")} />
                  ) : complete ? (
                    <Icon name="check" size={12} className="text-success" title={t("demo.steps.complete")} />
                  ) : null}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
