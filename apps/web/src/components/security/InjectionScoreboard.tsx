"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getScoreboard, rerunScoreboard, type Scoreboard } from "@/lib/api/security";
import { useApi } from "@/lib/useApi";

import { fmtDateTime, fmtN, fmtPct } from "./secText";

const BARS = [
  { mode: "off", label: "sec.sb.off", bar: "bg-danger" },
  { mode: "on", label: "sec.sb.on", bar: "bg-success" },
  { mode: "on_without_detector", label: "sec.sb.noDetector", bar: "bg-warning" },
] as const;

function Bar({ label, value, tone, n }: { label: string; value: number; tone: string; n?: number }) {
  const { lang } = useLang();
  const pct = Math.max(0, Math.min(1, value));
  const text = fmtPct(pct, lang);
  return (
    <li className="space-y-1" data-testid="sb-bar" data-value={pct}>
      <div className="flex justify-between gap-2 text-sm">
        <span className="font-semibold text-ink">{label}</span>
        <span className="font-bold tabular-nums text-ink">
          {text}
          {n != null ? <span className="font-normal text-muted"> (n={fmtN(n, lang)})</span> : null}
        </span>
      </div>
      <div aria-hidden="true" className="h-4 overflow-hidden rounded-full bg-surface-alt">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct * 100}%` }} />
      </div>
    </li>
  );
}

/** Presentational scoreboard: attack success rate per mode, detection quality, and a table alternative. */
export function ScoreboardView({
  data,
  onRerun,
  running,
}: {
  data: Scoreboard;
  onRerun: () => void;
  running: boolean;
}) {
  const t = useT();
  const { lang } = useLang();
  const modes = data.modes ?? {};
  const det = data.detection;
  const rerun = (
    <Button onClick={onRerun} disabled={running} aria-busy={running}>
      {running ? t("sec.sb.running") : data.available ? t("sec.sb.rerun") : t("sec.sb.run")}
    </Button>
  );
  return (
    <Card as="section" labelledBy="sb-h" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="sb-h" className="text-lg font-bold text-ink">
            {t("sec.sb.title")}
          </h2>
          <SimulatedBadge />
        </div>
        {rerun}
      </div>
      <p role="status" aria-live="polite" className="sr-only">
        {running ? t("sec.sb.running") : ""}
      </p>
      {!data.available ? (
        <p className="text-sm text-muted" data-testid="sb-empty">
          {t("sec.sb.empty")}
        </p>
      ) : (
        <>
          <p className="text-sm text-muted">
            {t("sec.sb.meta", {
              n: fmtN(data.attacks, lang),
              split: data.split,
              at: data.generated_at ? fmtDateTime(data.generated_at, lang) : "—",
            })}
          </p>
          <div>
            <h3 className="mb-2 text-sm font-bold text-ink">{t("sec.sb.asr")}</h3>
            <ul className="space-y-3">
              {BARS.filter((b) => modes[b.mode]).map((b) => (
                <Bar
                  key={b.mode}
                  label={t(b.label)}
                  value={modes[b.mode].attack_success_rate}
                  tone={b.bar}
                  n={modes[b.mode].n}
                />
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted">{t("sec.sb.moneyNote")}</p>
          </div>
          {det ? (
            <div>
              <h3 className="mb-2 text-sm font-bold text-ink">{t("sec.sb.detection")}</h3>
              <ul className="space-y-3">
                <Bar label={t("sec.sb.recall")} value={det.recall} tone="bg-success" />
                <Bar
                  label={t("sec.sb.fpr")}
                  value={det.false_positive_rate}
                  tone="bg-info"
                  n={det.clean_documents}
                />
              </ul>
              <p className="mt-1 text-xs text-muted">
                {t("sec.sb.clean", { n: fmtN(det.clean_documents, lang), fp: fmtN(det.false_positives, lang) })}
              </p>
            </div>
          ) : null}
          <p className="text-xs text-muted">{t("sec.sb.split")}</p>
          {data.notes ? <p className="text-xs text-muted">{data.notes}</p> : null}
          <table className="sr-only" data-testid="sb-table">
            <caption>{t("sec.sb.title")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("sec.sb.col.mode")}</th>
                <th scope="col">{t("sec.sb.col.n")}</th>
                <th scope="col">{t("sec.sb.asr")}</th>
              </tr>
            </thead>
            <tbody>
              {BARS.filter((b) => modes[b.mode]).map((b) => (
                <tr key={b.mode}>
                  <th scope="row">{t(b.label)}</th>
                  <td>{fmtN(modes[b.mode].n, lang)}</td>
                  <td>{fmtPct(modes[b.mode].attack_success_rate, lang)}</td>
                </tr>
              ))}
              {det ? (
                <>
                  <tr>
                    <th scope="row">{t("sec.sb.recall")}</th>
                    <td>{fmtN(data.attacks, lang)}</td>
                    <td>{fmtPct(det.recall, lang)}</td>
                  </tr>
                  <tr>
                    <th scope="row">{t("sec.sb.fpr")}</th>
                    <td>{fmtN(det.clean_documents, lang)}</td>
                    <td>{fmtPct(det.false_positive_rate, lang)}</td>
                  </tr>
                </>
              ) : null}
            </tbody>
          </table>
        </>
      )}
    </Card>
  );
}

export function InjectionScoreboard() {
  const sb = useApi((s) => getScoreboard(s), "inj-scoreboard");
  const [fresh, setFresh] = useState<Scoreboard | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  async function rerun() {
    setRunning(true);
    setErr(null);
    try {
      setFresh(await rerunScoreboard());
    } catch (e) {
      setErr(e);
    } finally {
      setRunning(false);
    }
  }

  const data = fresh ?? sb.data;
  if (sb.error && !data) return <QueryError error={sb.error} onRetry={sb.reload} />;
  if (!data) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-2">
      <ScoreboardView data={data} onRerun={rerun} running={running} />
      {err ? <QueryError error={err} onRetry={rerun} /> : null}
    </div>
  );
}
