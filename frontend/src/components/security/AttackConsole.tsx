"use client";

import { useState } from "react";

import { Badge, type Tone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import {
  getGallery,
  runAttack,
  type AttackSource,
  type ConsoleRunOut,
  type GalleryItem,
  type ToolAttempt,
} from "@/lib/api/security";
import { useApi } from "@/lib/useApi";

import { HighlightedText, RuleChips } from "./HighlightedText";
import { InjectionScoreboard } from "./InjectionScoreboard";
import { PipelineSteps } from "./PipelineSteps";
import { pickText } from "./secText";

const SOURCES: AttackSource[] = ["hidden_text", "visible_text", "metadata", "email"];
const focus =
  "focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

const OUTCOME: Record<ConsoleRunOut["outcome"], { tone: Tone; icon: string }> = {
  blocked: { tone: "success", icon: "✓" },
  stopped_by_risk_engine: { tone: "info", icon: "🛡" },
  no_effect: { tone: "neutral", icon: "○" },
  attack_succeeded: { tone: "danger", icon: "✕" },
};

function Attempts({ attempts }: { attempts: readonly ToolAttempt[] }) {
  const t = useT();
  if (attempts.length === 0) return <p className="text-sm text-muted">{t("sec.console.noAttempts")}</p>;
  return (
    <ul className="space-y-1.5" data-testid="attempts">
      {attempts.map((a, i) => (
        <li key={i} className="rounded-xl border border-line bg-surface-alt p-2.5 text-sm text-ink">
          <span className="font-mono font-semibold">{a.name}</span>
          {" — "}
          {a.outcome === "dropped_by_gate"
            ? t("sec.console.attempt.dropped")
            : a.outcome === "reached_service_then_risk_engine"
              ? t("sec.console.attempt.reached", {
                  tier: a.risk_tier ?? "?",
                  decision: a.risk_decision ?? "?",
                })
              : t("sec.console.attempt.executed")}
        </li>
      ))}
    </ul>
  );
}

function ResultCard({ run }: { run: ConsoleRunOut }) {
  const t = useT();
  const { lang } = useLang();
  const o = OUTCOME[run.outcome];
  const risk = run.attempts.find((a) => a.outcome === "reached_service_then_risk_engine");
  return (
    <Card as="section" labelledBy="res-h" className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="res-h" className="text-lg font-bold text-ink">
          {t("sec.console.result")}
        </h2>
        <Badge tone={o.tone} icon={o.icon}>
          {t(`sec.console.outcome.${run.outcome}`)}
        </Badge>
        <SimulatedBadge />
      </div>
      <p data-testid="result-text" className="text-xl font-bold text-ink">
        {pickText(lang, run.result_en, run.result_bn)}
      </p>
      {!run.defences && run.outcome === "stopped_by_risk_engine" && risk ? (
        <p role="note" className="rounded-xl border border-info bg-info-soft p-3 text-sm font-semibold text-ink">
          {t("sec.console.stoppedRisk", { tool: risk.name })}
        </p>
      ) : null}
      <p className="text-sm font-semibold text-ink">{t("sec.console.moneyNever")}</p>
      <div className="space-y-1">
        <h3 className="text-sm font-bold text-ink">{t("sec.console.attempts")}</h3>
        <Attempts attempts={run.attempts} />
      </div>
      <div className="space-y-1">
        <h3 className="text-sm font-bold text-ink">{t("sec.console.answer")}</h3>
        <p className="rounded-xl border border-line bg-surface-alt p-3 text-sm break-words whitespace-pre-wrap text-ink">
          {run.answer || t("sec.console.noAnswer")}
        </p>
      </div>
    </Card>
  );
}

export function AttackConsole() {
  const t = useT();
  const { lang } = useLang();
  const gallery = useApi((s) => getGallery(s), "inj-gallery");
  const [attackId, setAttackId] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [source, setSource] = useState<AttackSource>("hidden_text");
  const [defences, setDefences] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [run, setRun] = useState<ConsoleRunOut | null>(null);

  function pick(g: GalleryItem) {
    setAttackId(g.id);
    setText(g.text);
    setSource(g.source);
  }

  async function go() {
    setBusy(true);
    setError(null);
    try {
      setRun(await runAttack(attackId ? { attack_id: attackId, source, defences } : { text, source, defences }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const canRun = !busy && (attackId !== null || text.trim() !== "");
  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("sec.console.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="text-muted">{t("sec.console.intro")}</p>
      </header>

      <section aria-labelledby="gal-h" className="space-y-3">
        <h2 id="gal-h" className="text-lg font-bold text-ink">
          {t("sec.console.gallery")}
        </h2>
        {gallery.error ? (
          <QueryError error={gallery.error} onRetry={gallery.reload} />
        ) : !gallery.data ? (
          <Skeleton className="h-32" />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {gallery.data.items.map((g) => (
              <li key={g.id}>
                <button
                  type="button"
                  aria-pressed={attackId === g.id}
                  onClick={() => pick(g)}
                  className={`h-full w-full rounded-card border p-3 text-left shadow-card hover:shadow-card-hover ${focus} ${
                    attackId === g.id ? "border-brand-600 bg-brand-50" : "border-line bg-surface"
                  }`}
                >
                  <span className="block text-sm font-bold text-ink">{pickText(lang, g.label_en, g.label_bn)}</span>
                  <span className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted">
                    <span className="rounded-full border border-line px-2 py-0.5">{g.style}</span>
                    <span className="rounded-full border border-line px-2 py-0.5">{g.carrier_en}</span>
                    <span className="rounded-full border border-line px-2 py-0.5">{g.language}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="own-h" className="space-y-3">
        <h2 id="own-h" className="text-lg font-bold text-ink">
          {t("sec.console.own")}
        </h2>
        <div className="space-y-1">
          <label htmlFor="atk-text" className="block text-sm font-semibold text-ink">
            {t("sec.console.text")}
          </label>
          <textarea
            id="atk-text"
            rows={5}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setAttackId(null);
            }}
            className={`w-full rounded-xl border border-line bg-surface p-3 font-mono text-sm text-ink ${focus}`}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="atk-source" className="block text-sm font-semibold text-ink">
            {t("sec.console.placement")}
          </label>
          <select
            id="atk-source"
            value={source}
            onChange={(e) => setSource(e.target.value as AttackSource)}
            className={`rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink ${focus}`}
          >
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {t(`sec.source.${s}`)}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <span id="def-l" className="text-sm font-semibold text-ink">
            {t("sec.console.defences")}
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={defences}
            aria-labelledby="def-l"
            onClick={() => setDefences((d) => !d)}
            className={`inline-flex items-center gap-2 rounded-full border-2 px-3 py-1 text-sm font-bold ${focus} ${
              defences ? "border-success bg-success-soft text-success" : "border-danger bg-danger-soft text-danger"
            }`}
          >
            <span aria-hidden="true">{defences ? "✓" : "✕"}</span>
            {defences ? t("sec.console.on") : t("sec.console.off")}
          </button>
          <Button onClick={go} disabled={!canRun} aria-busy={busy}>
            {busy ? t("sec.console.running") : t("sec.console.run")}
          </Button>
        </div>
        {!defences ? (
          <div role="note" data-testid="off-banner" className="rounded-xl border-2 border-warning bg-warning-soft p-3 text-sm font-semibold text-ink">
            <span aria-hidden="true">▲ </span>
            {t("sec.console.offBanner")}
          </div>
        ) : null}
      </section>

      <div aria-live="polite" className="space-y-6">
        {error ? <QueryError error={error} onRetry={go} /> : null}
        {run ? (
          <>
            <section aria-labelledby="pipe-h" className="space-y-3">
              <h2 id="pipe-h" className="text-lg font-bold text-ink">
                {t("sec.console.pipeline")}
              </h2>
              <PipelineSteps key={run.event_id ?? run.text + run.defences + run.steps.length} steps={run.steps} />
            </section>
            <section aria-labelledby="det-h" className="space-y-2">
              <h2 id="det-h" className="text-lg font-bold text-ink">
                {t("sec.console.detection")}
              </h2>
              <HighlightedText text={run.text} highlights={run.detection?.highlights ?? []} />
              {run.detection ? (
                <>
                  <p className="text-sm text-ink">
                    {t("sec.console.score")}: <strong data-testid="det-score">{run.detection.score}</strong>
                    {" · "}
                    {run.detection.is_injection ? t("sec.console.injection") : t("sec.console.clean")}
                  </p>
                  <RuleChips rules={run.detection.matched_rules} />
                </>
              ) : (
                <p className="text-sm text-muted">{t("sec.console.noDetection")}</p>
              )}
            </section>
            <ResultCard run={run} />
          </>
        ) : null}
      </div>

      <InjectionScoreboard />
    </div>
  );
}
