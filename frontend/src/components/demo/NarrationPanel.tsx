"use client";

import { Badge, type Tone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useLang, useT } from "@/i18n";
import type { DemoTag, SceneResult } from "@/lib/api/demo";
import type { Problem } from "./useDemoRun";

import { biText, toDemoLang, type FlatScene } from "./demoModel";
import { FactsList } from "./Facts";

export const TAG_STYLE: Record<DemoTag, { tone: Tone; icon: IconName }> = {
  TASK: { tone: "info", icon: "check" },
  SECURITY: { tone: "warning", icon: "shield" },
  INNOVATION: { tone: "success", icon: "sparkle" },
};

export function TagChip({ tag }: { tag: DemoTag }) {
  const t = useT();
  const s = TAG_STYLE[tag];
  return (
    <Badge tone={s.tone} icon={<Icon name={s.icon} size={12} />}>
      {t(`demo.tag.${tag}`)}
    </Badge>
  );
}

type Props = {
  current: FlatScene | null;
  result: SceneResult | null;
  busy: boolean;
  problem: Problem | null;
  rateWait: number | null;
  onRetry: () => void;
  onNext: () => void;
};

export function NarrationPanel({ current, result, busy, problem, rateWait, onRetry, onNext }: Props) {
  const t = useT();
  const lang = toDemoLang(useLang().lang);
  if (!current) {
    return (
      <section aria-labelledby="demo-story-h" className="space-y-2">
        <h2 id="demo-story-h" className="text-lg font-bold text-ink">
          {t("demo.story.idleTitle")}
        </h2>
        <p className="text-sm text-muted">{t("demo.story.idleBody")}</p>
      </section>
    );
  }
  const failed = result?.status === "failed";
  const failedAssertions = (result?.assertions ?? []).filter((a) => !a.ok);
  return (
    <section aria-labelledby="demo-story-h" className="space-y-3" data-testid="narration">
      <div className="flex flex-wrap items-center gap-2">
        <TagChip tag={current.step.tag} />
        <span className="text-xs font-semibold text-muted">
          {t("demo.progress", { step: current.n, pos: current.pos, count: current.count })}
        </span>
      </div>
      <h2 id="demo-story-h" className="text-xl font-extrabold text-ink">
        {biText(current.step.title, lang)}
      </h2>
      <p className="text-sm text-ink">{biText(current.step.narration, lang)}</p>
      <p aria-live="polite" data-testid="caption" className="rounded-xl border border-brand-700 bg-brand-50 p-3 text-sm font-semibold text-ink">
        {biText(current.scene.caption, lang)}
      </p>

      {rateWait ? (
        <p role="status" className="rounded-xl border border-warning bg-warning-soft p-3 text-sm font-medium text-warning">
          {t("demo.err.rate", { s: rateWait })}
        </p>
      ) : null}

      {problem && !busy ? (
        <div role="alert" className="space-y-2 rounded-xl border border-danger bg-danger-soft p-3 text-sm text-danger">
          <p className="font-semibold">{t(`demo.err.${problem.kind}`, { s: 5 })}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={onRetry}>
              {t("demo.err.retry")}
            </Button>
            <Button size="sm" variant="secondary" onClick={onNext}>
              {t("demo.err.skip")}
            </Button>
          </div>
        </div>
      ) : null}

      {failed ? (
        <div role="status" data-testid="scene-failed" className="space-y-2 rounded-xl border border-warning bg-warning-soft p-3 text-sm text-ink">
          <p className="flex items-start gap-2 font-semibold">
            <Icon name="warn" size={16} className="mt-0.5 shrink-0 text-warning" />
            <span>{biText(result?.message, lang) || t("demo.scene.failedDefault")}</span>
          </p>
          <p className="text-muted">{t("demo.scene.failedHint")}</p>
          {failedAssertions.length > 0 ? (
            <details>
              <summary className="cursor-pointer rounded font-semibold text-brand-text focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
                {t("demo.scene.details")}
              </summary>
              <ul className="mt-2 space-y-1">
                {failedAssertions.map((a, i) => (
                  <li key={i} className="text-xs">
                    <span className="font-semibold">{biText(a.label, lang)}</span>
                    {" – "}
                    {t("demo.assert.expected")}: <code>{a.expected}</code> · {t("demo.assert.actual")}: <code>{a.actual}</code>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      ) : null}

      <FactsList facts={result?.facts} />

      {result && result.assertions && result.assertions.length > 0 ? (
        <div>
          <h3 className="text-sm font-bold text-ink">{t("demo.assert.title")}</h3>
          <ul className="mt-1 space-y-1" data-testid="assertions">
            {result.assertions.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-ink">
                <Icon name={a.ok ? "check" : "x"} size={14} className={`mt-0.5 shrink-0 ${a.ok ? "text-success" : "text-danger"}`} />
                <span className="min-w-0">
                  <span className="sr-only">{a.ok ? t("demo.assert.ok") : t("demo.assert.fail")}: </span>
                  <span className="font-semibold">{biText(a.label, lang)}</span>
                  <span className="block text-muted">
                    {t("demo.assert.expected")} <code className="text-ink">{a.expected}</code> · {t("demo.assert.actual")}{" "}
                    <code className="text-ink">{a.actual}</code>
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
