"use client";

import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import type { DemoSandbox } from "@/lib/api/demo";

type Props = {
  sandbox: DemoSandbox | null;
  busy: boolean;
  readAloud: boolean;
  speechSupported: boolean;
  note: string | null;
  onLiveAi: (on: boolean) => void;
  onReadAloud: (on: boolean) => void;
  onSkipCooling: () => void;
  onReset: () => void;
  onEnd: () => void;
  onReloadFrame: () => void;
};

export function ToolsPanel({ sandbox, busy, readAloud, speechSupported, note, onLiveAi, onReadAloud, onSkipCooling, onReset, onEnd, onReloadFrame }: Props) {
  const t = useT();
  const available = Boolean(sandbox?.live_ai_available);
  return (
    <section aria-labelledby="demo-tools-h" className="space-y-3">
      <h2 id="demo-tools-h" className="text-lg font-bold text-ink">
        {t("demo.tools.title")}
      </h2>
      <div>
        <label className="flex min-h-11 items-center gap-2 text-sm font-semibold text-ink">
          <input
            type="checkbox"
            checked={Boolean(sandbox?.live_ai)}
            disabled={!available || busy}
            onChange={(e) => onLiveAi(e.target.checked)}
            aria-describedby="demo-liveai-hint"
            className="size-5 accent-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500"
          />
          {t("demo.tools.liveAi")}
        </label>
        <p id="demo-liveai-hint" className="text-xs text-muted">
          {!available
            ? t("demo.tools.liveAiOff")
            : sandbox?.live_ai
              ? t("demo.tools.liveAiBudget", { n: sandbox.live_ai_budget_left })
              : t("demo.tools.liveAiHint", { n: sandbox?.live_ai_budget_left ?? 0 })}
        </p>
      </div>
      {speechSupported ? (
        <label className="flex min-h-11 items-center gap-2 text-sm font-semibold text-ink">
          <input
            type="checkbox"
            checked={readAloud}
            onChange={(e) => onReadAloud(e.target.checked)}
            className="size-5 accent-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500"
          />
          {t("demo.tools.readAloud")}
        </label>
      ) : null}
      <div>
        <Button variant="secondary" size="sm" onClick={onSkipCooling} disabled={busy} aria-describedby="demo-skip-hint">
          {t("demo.tools.skipCooling")}
        </Button>
        <p id="demo-skip-hint" className="mt-1 text-xs text-muted">
          {t("demo.tools.skipHint")}
        </p>
        {note ? (
          <p role="status" className="mt-1 text-xs font-semibold text-success">
            {note}
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" onClick={onReloadFrame}>
          {t("demo.tools.reloadFrame")}
        </Button>
        <Button variant="secondary" size="sm" onClick={onReset} disabled={busy}>
          {t("demo.tools.reset")}
        </Button>
        <Button variant="danger" size="sm" onClick={onEnd}>
          {t("demo.tools.end")}
        </Button>
      </div>
    </section>
  );
}
