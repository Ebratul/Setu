"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";
import { tamperDemo, type AuditEntry, type TamperOut } from "@/lib/api/audit";

import { reasonKey } from "./auditText";
import { ChainBlocks } from "./ChainBlocks";
import { currentValue, defaultField, editableFields, suggestValue, type TamperMode } from "./tamperModel";

const focus = "focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";
const field = `w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink ${focus}`;

type Props = { entries: readonly AuditEntry[]; initialSeq?: number | null };

/** Change, delete or swap an entry of a server-side COPY and watch verification break. */
export function TamperPanel({ entries, initialSeq = null }: Props) {
  const t = useT();
  const preferred = useMemo(
    () => entries.find((e) => e.seq === initialSeq) ?? [...entries].reverse().find((e) => "amount" in e.payload) ?? entries[entries.length - 1],
    [entries, initialSeq],
  );
  const [seqSel, setSeqSel] = useState<number | null>(null);
  const [mode, setMode] = useState<TamperMode>("edit");
  const [fieldSel, setFieldSel] = useState<string | null>(null);
  const [valueSel, setValueSel] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<TamperOut | null>(null);

  const seq = seqSel ?? preferred?.seq ?? null;
  const entry = entries.find((e) => e.seq === seq);
  const fields = entry ? editableFields(entry) : [];
  const f = fieldSel && fields.includes(fieldSel) ? fieldSel : entry ? defaultField(entry) : "";
  const value = valueSel ?? (entry && f ? suggestValue(entry, f) : "");

  async function run() {
    if (!entry) return;
    setBusy(true);
    setError(null);
    try {
      setResult(
        await tamperDemo({
          mode,
          seq: entry.seq,
          ...(mode === "edit" ? { field: f, value } : {}),
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const report = result?.report;
  const missing = report && !report.ok && report.reason === "missing_seq" ? report.broken_seq : null;
  return (
    <Card as="section" labelledBy="tamper-h" className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="tamper-h" className="text-lg font-bold text-ink">
          {t("audit.tamper.title")}
        </h2>
        <SimulatedBadge />
      </div>
      <p className="text-sm text-muted">{t("audit.tamper.intro")}</p>

      {entries.length === 0 ? (
        <p className="text-sm text-muted">{t("audit.tamper.noEntries")}</p>
      ) : (
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(ev) => {
            ev.preventDefault();
            void run();
          }}
        >
          <div>
            <label htmlFor="tp-seq" className="mb-1 block text-sm font-semibold text-ink">
              {t("audit.tamper.entry")}
            </label>
            <select
              id="tp-seq"
              className={field}
              value={seq ?? ""}
              onChange={(ev) => {
                setSeqSel(Number(ev.target.value));
                setFieldSel(null);
                setValueSel(null);
              }}
            >
              {entries.map((e) => (
                <option key={e.seq} value={e.seq}>
                  #{e.seq} {e.action}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="tp-mode" className="mb-1 block text-sm font-semibold text-ink">
              {t("audit.tamper.modeLabel")}
            </label>
            <select id="tp-mode" className={field} value={mode} onChange={(ev) => setMode(ev.target.value as TamperMode)}>
              <option value="edit">{t("audit.tamper.mode.edit")}</option>
              <option value="delete">{t("audit.tamper.mode.delete")}</option>
              <option value="reorder">{t("audit.tamper.mode.reorder")}</option>
            </select>
          </div>
          {mode === "edit" ? (
            <>
              <div>
                <label htmlFor="tp-field" className="mb-1 block text-sm font-semibold text-ink">
                  {t("audit.tamper.field")}
                </label>
                <select
                  id="tp-field"
                  className={field}
                  value={f}
                  onChange={(ev) => {
                    setFieldSel(ev.target.value);
                    setValueSel(null);
                  }}
                >
                  {fields.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="tp-value" className="mb-1 block text-sm font-semibold text-ink">
                  {t("audit.tamper.value")}
                </label>
                <input id="tp-value" className={field} value={value} onChange={(ev) => setValueSel(ev.target.value)} />
                {entry && f ? (
                  <p className="mt-1 text-xs text-muted">{t("audit.tamper.was", { value: currentValue(entry, f) })}</p>
                ) : null}
              </div>
            </>
          ) : (
            <p className="self-end text-sm text-muted sm:col-span-2">
              {mode === "delete" ? t("audit.tamper.deleteHelp") : t("audit.tamper.reorderHelp")}
            </p>
          )}
          <div className="sm:col-span-2 lg:col-span-4">
            <Button type="submit" disabled={busy || !entry}>
              {busy ? t("audit.tamper.running") : t("audit.tamper.run")}
            </Button>
          </div>
        </form>
      )}

      {error ? <QueryError error={error} onRetry={() => void run()} /> : null}

      <div aria-live="polite" data-testid="tamper-result">
        {result && report ? (
          <div className="space-y-3">
            <p role="note" className="rounded-xl border-2 border-warning bg-warning-soft p-3 text-sm font-semibold text-ink">
              <span aria-hidden="true">⚠ </span>
              {t("audit.tamper.banner")}
            </p>
            <p
              className={`rounded-xl border-2 p-3 text-sm font-semibold text-ink ${report.ok ? "border-success bg-success-soft" : "border-danger bg-danger-soft"}`}
              data-testid="tamper-verdict"
            >
              <span aria-hidden="true">{report.ok ? "✓ " : "✕ "}</span>
              {report.ok
                ? t("audit.tamper.stillOk")
                : t("audit.result.broken", { seq: report.broken_seq ?? "?", reason: t(reasonKey(report.reason)) })}
              {report.detail ? <span className="mt-1 block text-xs font-normal text-muted">{report.detail}</span> : null}
            </p>
            <ChainBlocks
              judge
              entries={result.entries}
              brokenFrom={report.ok ? null : report.broken_seq}
              missingSeq={missing}
              label={t("audit.tamper.chainLabel")}
            />
            <Button
              variant="secondary"
              onClick={() => {
                setResult(null);
                setError(null);
              }}
            >
              {t("audit.tamper.restore")}
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
