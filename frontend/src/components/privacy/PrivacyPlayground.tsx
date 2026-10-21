"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import { privacyDryRun } from "@/lib/api/privacy";
import { typeMeta } from "@/lib/privacy/segments";
import type { DryRunResult } from "@/lib/privacy/types";
import { useApi, useDebounced } from "@/lib/useApi";

import { PrivacyBadge } from "./PrivacyBadge";
import { countsLine, fmtNum, typeLabel } from "./privacyText";
import { SegmentText } from "./SegmentText";

export const SAMPLE_TEXT = `Rahima: আমার supplier-এর account নম্বর 6222 0021 4455 7788-এ কি টাকা যাবে?

Proforma Invoice PI-2026-0042
Seller: Ningbo Hengda Trading Co. — A/C 6222 0021 4455 7788, SWIFT: ICBKCNBJNBO
Contact: Chen Wei · +86 138 0013 8000 · rahima@example.com
Director NID 1990123456789 · mobile +8801711223344
Total: USD 11,200.00 · Advance 30%: BDT 1,560`;

const OBFUSCATION = [
  { key: "obfSpaced", value: "0 1 7 1 1 2 2 3 3 4 4" },
  { key: "obfBangla", value: "০১৭১১ ২২৩ ৩৪৪" },
  { key: "obfZwj", value: "01711‍223344" },
] as const;

const focusRing =
  "focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";
const th = "px-3 py-2 text-left font-semibold";
const td = "px-3 py-2 align-top";

type Sent = { key: string; result: DryRunResult } | { key: string; failed: true };

export function PrivacyPlayground() {
  const t = useT();
  const { lang } = useLang();
  const [text, setText] = useState(SAMPLE_TEXT);
  const [maskAmounts, setMaskAmounts] = useState(true);
  const [showObf, setShowObf] = useState(false);
  const [sent, setSent] = useState<Sent | null>(null);
  const [sending, setSending] = useState(false);
  const debounced = useDebounced(text, 300);
  const key = `${maskAmounts}|${text}`;

  const live = useApi(
    (s) => privacyDryRun({ text: debounced, mask_amounts: maskAmounts }, s),
    `privacy-dry|${maskAmounts}|${debounced}`,
    debounced.trim() !== "",
  );
  const pending = debounced !== text || live.loading;
  const result = debounced.trim() === "" ? undefined : live.data;

  function insert(example: string) {
    setText((v) => (v === "" || v.endsWith("\n") ? v : `${v}\n`) + example);
  }

  async function send() {
    const sentKey = key;
    setSending(true);
    try {
      const r = await privacyDryRun({ text, mask_amounts: maskAmounts });
      setSent({ key: sentKey, result: r });
    } catch {
      setSent({ key: sentKey, failed: true });
    } finally {
      setSending(false);
    }
  }

  const hits = result?.hits ?? [];
  const status = pending
    ? t("privacy.pg.checking")
    : result
      ? hits.length === 0
        ? t("privacy.pg.found.none")
        : t(hits.length === 1 ? "privacy.pg.found.one" : "privacy.pg.found.other", { n: fmtNum(hits.length, lang) })
      : "";
  const shown = sent && sent.key === key ? sent : null;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("privacy.pg.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="text-muted">{t("privacy.pg.intro")}</p>
        <p
          className="inline-block rounded-xl border border-info bg-info-soft px-3 py-1 text-sm font-semibold text-info"
          data-testid="dry-run-note"
        >
          <span aria-hidden="true">ℹ </span>
          {t("privacy.pg.note")}
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card as="section" labelledBy="ppg-input-h" className="min-w-0 space-y-4">
          <h2 id="ppg-input-h" className="text-lg font-bold text-ink">
            {t("privacy.pg.input")}
          </h2>
          <div>
            <label htmlFor="ppg-text" className="sr-only">
              {t("privacy.pg.input")}
            </label>
            <textarea
              id="ppg-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={12}
              spellCheck={false}
              className={`w-full rounded-xl border border-line bg-surface px-3 py-2 font-mono text-sm text-ink ${focusRing}`}
            />
          </div>
          <ul className="space-y-2">
            <li>
              <label className="flex cursor-pointer items-center gap-3 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={maskAmounts}
                  onChange={(e) => setMaskAmounts(e.target.checked)}
                  className={`size-5 accent-brand-700 ${focusRing}`}
                />
                {t("privacy.pg.maskAmounts")}
              </label>
            </li>
            <li>
              <label className="flex cursor-pointer items-center gap-3 text-sm text-ink">
                <input
                  type="checkbox"
                  checked={showObf}
                  onChange={(e) => setShowObf(e.target.checked)}
                  className={`size-5 accent-brand-700 ${focusRing}`}
                />
                {t("privacy.pg.showObf")}
              </label>
            </li>
          </ul>
          {showObf ? (
            <div role="group" aria-label={t("privacy.pg.obfIntro")} className="space-y-2">
              <p className="text-sm text-muted">{t("privacy.pg.obfIntro")}</p>
              <div className="flex flex-wrap gap-2">
                {OBFUSCATION.map((o) => (
                  <Button key={o.key} variant="secondary" onClick={() => insert(o.value)} data-testid={`insert-${o.key}`}>
                    {t(`privacy.pg.${o.key}`)}
                  </Button>
                ))}
              </div>
            </div>
          ) : null}
        </Card>

        <section aria-labelledby="ppg-live-h" className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 id="ppg-live-h" className="text-lg font-bold text-ink">
              {t("privacy.pg.live")}
            </h2>
            {pending ? (
              <span
                aria-hidden="true"
                className="size-4 animate-spin rounded-full border-2 border-brand-600 border-t-transparent motion-reduce:animate-none"
              />
            ) : null}
            <p role="status" aria-live="polite" className="text-sm text-muted" data-testid="live-status">
              {status}
            </p>
          </div>
          {live.error ? (
            <QueryError error={live.error} onRetry={live.reload} />
          ) : result ? (
            <Card className="space-y-4">
              <div className="text-sm text-ink" data-testid="live-source">
                <SegmentText segments={result.source_segments} />
              </div>
              <p className="text-sm font-semibold text-ink">
                {countsLine(t, lang, result.stats.masked_by_type, result.stats.protected)}
              </p>
              <HitsTable result={result} />
            </Card>
          ) : null}
        </section>
      </div>

      <section aria-labelledby="ppg-send-h" className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="ppg-send-h" className="text-lg font-bold text-ink">
            {t("privacy.pg.results")}
          </h2>
          <Button onClick={send} disabled={sending || text.trim() === ""} data-testid="send-dry-run">
            {sending ? t("privacy.pg.sending") : t("privacy.pg.send")}
          </Button>
          <SimulatedBadge />
          <span className="text-sm font-semibold text-info">{t("privacy.pg.note")}</span>
        </div>
        <div aria-live="polite">
          {shown && "failed" in shown ? (
            <p role="alert" className="text-sm font-medium text-danger">
              {t("privacy.pg.error")}
            </p>
          ) : shown ? (
            <div className="grid gap-4 lg:grid-cols-3" data-testid="dry-run-panes">
              <Pane id="masked" title={t("privacy.pg.paneMasked")} segments={shown.result.masked_segments} mono>
                <div className="flex flex-wrap gap-2">
                  <PrivacyBadge kind="protected" count={shown.result.stats.protected} />
                  <PrivacyBadge kind="leaked" count={shown.result.stats.leaked_count} />
                </div>
              </Pane>
              <Pane id="answer" title={t("privacy.pg.paneAnswer")} segments={shown.result.ai_answer_segments} mono />
              <Pane id="restored" title={t("privacy.pg.paneRestored")} segments={shown.result.restored_segments} />
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function Pane({
  id,
  title,
  segments,
  mono = false,
  children,
}: {
  id: string;
  title: string;
  segments: DryRunResult["masked_segments"];
  mono?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <Card as="section" labelledBy={`ppg-pane-${id}`} className="min-w-0 space-y-2">
      <h3 id={`ppg-pane-${id}`} className="text-sm font-bold text-ink">
        {title}
      </h3>
      {children}
      <div className="text-sm text-ink" data-testid={`pane-${id}`}>
        <SegmentText segments={segments} mono={mono} />
      </div>
    </Card>
  );
}

function HitsTable({ result }: { result: DryRunResult }) {
  const t = useT();
  const { lang } = useLang();
  if (result.hits.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-96 text-sm" data-testid="hits-table">
        <caption className="sr-only">{t("privacy.pg.detections")}</caption>
        <thead>
          <tr className="border-b border-line text-muted">
            <th scope="col" className={th}>{t("privacy.pg.col.type")}</th>
            <th scope="col" className={th}>{t("privacy.pg.col.token")}</th>
            <th scope="col" className={`${th} text-right`}>{t("privacy.pg.col.confidence")}</th>
            <th scope="col" className={th}>{t("privacy.pg.col.handling")}</th>
          </tr>
        </thead>
        <tbody>
          {result.hits.map((h, i) => {
            const meta = typeMeta(h.type);
            const label =
              lang === "bn" ? h.label_bn || h.label_en : lang === "zh" ? typeLabel(t, h.type, 1) : h.label_en || h.type;
            return (
              <tr key={`${h.token}-${i}`} className="border-b border-line last:border-0" data-testid="hit-row" data-type={h.type}>
                <td className={td}>
                  <span aria-hidden="true">{meta.icon} </span>
                  {label}
                </td>
                <td className={`${td} font-mono`}>{h.token}</td>
                <td className={`${td} text-right tabular-nums`}>
                  {new Intl.NumberFormat(lang === "bn" ? "bn-BD" : lang === "zh" ? "zh-CN" : "en-US", {
                    style: "percent",
                    maximumFractionDigits: 0,
                  }).format(h.confidence)}
                </td>
                <td className={td}>
                  {h.obfuscated ? (
                    <span
                      data-testid="obfuscated-badge"
                      className="inline-flex items-center gap-1 rounded-full border border-warning bg-warning-soft px-2.5 py-0.5 text-xs font-semibold text-warning"
                    >
                      <span aria-hidden="true">≈</span>
                      {t("privacy.pg.obfHandled")}
                    </span>
                  ) : (
                    t("privacy.pg.direct")
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
