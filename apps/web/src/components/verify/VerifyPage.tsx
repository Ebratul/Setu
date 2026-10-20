"use client";

import Link from "next/link";
import { useEffect, useState, type DragEvent } from "react";

import { CopyChip } from "@/components/approvals/CopyChip";
import { reasonKey } from "@/components/audit/auditText";
import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { Card } from "@/components/ui/Card";
import { useT } from "@/i18n";
import { parseReceiptUrl } from "@/lib/audit/receipt";
import {
  AuditParseError,
  fingerprint,
  parseExport,
  parsePublicKeyPem,
  verifyLines,
  verifySingle,
  type AuditLine,
  type VerifyReport,
} from "@/lib/audit/verify";
import { useApi } from "@/lib/useApi";
import { useHref } from "@/lib/useHref";

import { readFileText } from "./readFile";

const focus = "focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";
const fileInput = `block w-full text-sm text-ink file:mr-3 file:rounded-xl file:border-0 file:bg-brand-700 file:px-4 file:py-2 file:font-semibold file:text-white hover:file:bg-brand-800 ${focus} rounded-xl`;

type LogResult =
  | { kind: "report"; report: VerifyReport; entries: AuditLine[]; fingerprint: string; name: string }
  | { kind: "error"; message: string };

type ReceiptResult =
  | { kind: "report"; report: VerifyReport; hashMatches: boolean | null; seq: number; fingerprint: string }
  | { kind: "error"; message: string };

const loadDefaultKey = (s: AbortSignal) =>
  fetch("/audit-public-key.pem", { signal: s, cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error("key");
    return r.text();
  });

function Verdict({ ok, children, testId }: { ok: boolean; children: React.ReactNode; testId: string }) {
  return (
    <div
      data-testid={testId}
      data-ok={ok}
      className={`rounded-card border-2 p-4 text-ink ${ok ? "border-success bg-success-soft" : "border-danger bg-danger-soft"}`}
    >
      <p className={`text-lg font-bold ${ok ? "text-success" : "text-danger"}`}>
        <span aria-hidden="true">{ok ? "✓ " : "✕ "}</span>
        {children}
      </p>
    </div>
  );
}

export function VerifyPage() {
  const t = useT();
  const href = useHref();
  const defaultKey = useApi(loadDefaultKey, "audit-default-pem");
  const [customPem, setCustomPem] = useState<{ name: string; pem: string } | null>(null);
  const [logText, setLogText] = useState<{ name: string; text: string } | null>(null);
  const [log, setLog] = useState<LogResult | null>(null);
  const [receipt, setReceipt] = useState<ReceiptResult | null>(null);
  const [fpDefault, setFpDefault] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const pem = customPem?.pem ?? defaultKey.data ?? null;
  const rp = href ? parseReceiptUrl(href) : { seq: null, hash: null, entry: null };

  useEffect(() => {
    if (!defaultKey.data) return;
    let live = true;
    fingerprint(parsePublicKeyPem(defaultKey.data)).then((f) => live && setFpDefault(f), () => undefined);
    return () => {
      live = false;
    };
  }, [defaultKey.data]);

  async function verifyLog(name: string, text: string, keyPem: string | null) {
    if (!keyPem) {
      setLog({ kind: "error", message: t("audit.verify.noKey") });
      return;
    }
    try {
      const key = parsePublicKeyPem(keyPem);
      const { header, entries } = parseExport(text);
      if (entries.length === 0) {
        setLog({ kind: "error", message: t("audit.verify.empty") });
        return;
      }
      const report = await verifyLines(entries, key, { contiguous: header ? header.contiguous !== false : true });
      setLog({ kind: "report", report, entries, fingerprint: await fingerprint(key), name });
    } catch (e) {
      setLog({
        kind: "error",
        message: e instanceof AuditParseError ? t("audit.verify.parseError", { detail: e.message }) : t("audit.verify.readError"),
      });
    }
  }

  async function onLog(file: File | undefined) {
    if (!file) return;
    const text = await readFileText(file).catch(() => null);
    if (text === null) {
      setLog({ kind: "error", message: t("audit.verify.readError") });
      return;
    }
    setLogText({ name: file.name, text });
    await verifyLog(file.name, text, pem);
  }

  async function onKey(file: File | undefined) {
    if (!file) return;
    const text = await readFileText(file).catch(() => null);
    if (text === null) return;
    try {
      parsePublicKeyPem(text);
    } catch {
      setLog({ kind: "error", message: t("audit.verify.badKey") });
      return;
    }
    setCustomPem({ name: file.name, pem: text });
    if (logText) await verifyLog(logText.name, logText.text, text);
  }

  const receiptEntry = rp.entry;
  useEffect(() => {
    if (!receiptEntry || !pem) return;
    let live = true;
    (async () => {
      try {
        const key = parsePublicKeyPem(pem);
        const report = await verifySingle(receiptEntry, key);
        const e = receiptEntry as { entry_hash?: unknown; seq?: unknown };
        const hashMatches = rp.hash ? e.entry_hash === rp.hash : null;
        if (live) setReceipt({ kind: "report", report, hashMatches, seq: Number(e.seq), fingerprint: await fingerprint(key) });
      } catch {
        if (live) setReceipt({ kind: "error", message: t("audit.verify.badKey") });
      }
    })();
    return () => {
      live = false;
    };
  }, [receiptEntry, pem, rp.hash, t]);

  function onDrop(e: DragEvent<HTMLElement>) {
    e.preventDefault();
    setDragging(false);
    void onLog(e.dataTransfer.files[0]);
  }

  const highlight = rp.seq && !receiptEntry && log?.kind === "report" ? log.entries.find((e) => e.seq === rp.seq) : undefined;

  return (
    <>
      <header className="border-b border-line bg-surface shadow-card">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link href="/" className={`rounded text-lg font-bold text-brand-text ${focus}`}>
            Setu সেতু
          </Link>
          <LanguageToggle withZh />
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-4xl flex-1 space-y-6 px-4 py-8">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-ink">{t("audit.verify.title")}</h1>
          <p className="text-muted">{t("audit.verify.intro")}</p>
          <p className="rounded-xl border border-info bg-info-soft p-3 text-sm text-ink" data-testid="privacy-note">
            <span aria-hidden="true">🔒 </span>
            {t("audit.verify.privacy")}
          </p>
        </div>

        {receiptEntry ? (
          <section aria-labelledby="rc-h" className="space-y-3" data-testid="receipt-check">
            <h2 id="rc-h" className="text-lg font-bold text-ink">
              {t("audit.verify.receiptTitle")}
            </h2>
            <div aria-live="polite">
              {!receipt ? (
                <p className="text-sm text-muted">{t("audit.verify.checking")}</p>
              ) : receipt.kind === "error" ? (
                <Verdict ok={false} testId="receipt-result">
                  {receipt.message}
                </Verdict>
              ) : receipt.report.ok && receipt.hashMatches !== false ? (
                <>
                  <Verdict ok testId="receipt-result">
                    {t("audit.verify.receiptOk", { seq: receipt.seq })}
                  </Verdict>
                  <p className="mt-2 text-sm text-muted">{t("audit.verify.singleNote")}</p>
                </>
              ) : (
                <>
                  <Verdict ok={false} testId="receipt-result">
                    {receipt.report.ok
                      ? t("audit.verify.hashDiffers")
                      : t("audit.result.broken", { seq: receipt.report.brokenSeq ?? "?", reason: t(reasonKey(receipt.report.reason)) })}
                  </Verdict>
                  {receipt.report.reason ? <p className="mt-2 text-sm text-ink">{t(`audit.explain.${receipt.report.reason}`)}</p> : null}
                </>
              )}
            </div>
          </section>
        ) : rp.seq ? (
          <p className="rounded-xl border border-warning bg-warning-soft p-3 text-sm text-ink" data-testid="receipt-instructions">
            <span aria-hidden="true">ℹ </span>
            {t("audit.verify.receiptInstructions", { seq: rp.seq })}
          </p>
        ) : null}

        <Card as="section" labelledBy="up-h" className="space-y-4">
          <h2 id="up-h" className="text-lg font-bold text-ink">
            {t("audit.verify.uploadTitle")}
          </h2>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`space-y-2 rounded-card border-2 border-dashed p-6 ${dragging ? "border-brand-500 bg-brand-50" : "border-line bg-surface-alt"}`}
          >
            <label htmlFor="log-file" className="block text-sm font-semibold text-ink">
              {t("audit.verify.logLabel")}
            </label>
            <input
              id="log-file"
              type="file"
              accept=".jsonl,.ndjson,.json,application/x-ndjson,application/json,text/plain"
              className={fileInput}
              data-testid="log-input"
              onChange={(e) => void onLog(e.target.files?.[0])}
            />
            <p className="text-xs text-muted">{t("audit.verify.dropHint")}</p>
          </div>

          <div className="space-y-1 text-sm" data-testid="key-info">
            <p className="font-semibold text-ink">{customPem ? t("audit.verify.keyCustom", { name: customPem.name }) : t("audit.verify.keyDefault")}</p>
            {fpDefault && !customPem ? (
              <CopyChip
                text={`${fpDefault.slice(0, 16)}…${fpDefault.slice(-6)}`}
                copyValue={fpDefault}
                ariaLabel={t("audit.evidence.copyFingerprint")}
                copiedLabel={t("audit.copied")}
              />
            ) : null}
            {defaultKey.error && !customPem ? <p className="text-danger">{t("audit.verify.noKey")}</p> : null}
          </div>

          <details className="rounded-xl border border-line p-3">
            <summary className={`cursor-pointer rounded text-sm font-semibold text-ink ${focus}`}>{t("audit.verify.advanced")}</summary>
            <div className="mt-3 space-y-2">
              <label htmlFor="key-file" className="block text-sm font-semibold text-ink">
                {t("audit.verify.keyLabel")}
              </label>
              <input
                id="key-file"
                type="file"
                accept=".pem,text/plain"
                className={fileInput}
                data-testid="key-input"
                onChange={(e) => void onKey(e.target.files?.[0])}
              />
            </div>
          </details>
        </Card>

        <section aria-labelledby="res-h" className="space-y-3">
          <h2 id="res-h" className="text-lg font-bold text-ink">
            {t("audit.verify.resultTitle")}
          </h2>
          <div aria-live="polite" data-testid="log-result-region">
            {!log ? (
              <p className="text-sm text-muted">{t("audit.verify.waiting")}</p>
            ) : log.kind === "error" ? (
              <Verdict ok={false} testId="log-result">
                {log.message}
              </Verdict>
            ) : log.report.ok ? (
              <div className="space-y-2">
                <Verdict ok testId="log-result">
                  {t("audit.result.ok", { n: log.report.entriesChecked, a: log.report.firstSeq ?? "-", b: log.report.lastSeq ?? "-" })}
                </Verdict>
                {log.report.missingSeqs > 0 ? (
                  <p className="text-sm font-semibold text-warning" role="status">
                    {t("audit.verify.partial", { n: log.report.missingSeqs })}
                  </p>
                ) : null}
                {!log.report.anchored ? <p className="text-sm text-muted">{t("audit.verify.notAnchored")}</p> : null}
              </div>
            ) : (
              <div className="space-y-2">
                <Verdict ok={false} testId="log-result">
                  {t("audit.result.broken", { seq: log.report.brokenSeq ?? "?", reason: t(reasonKey(log.report.reason)) })}
                </Verdict>
                {log.report.reason ? <p className="text-sm text-ink">{t(`audit.explain.${log.report.reason}`)}</p> : null}
                {log.report.detail ? <p className="text-xs text-muted">{log.report.detail}</p> : null}
              </div>
            )}
            {log?.kind === "report" ? (
              <p className="mt-2 text-xs text-muted">{t("audit.verify.checkedWith", { file: log.name, fp: log.fingerprint.slice(0, 16) })}</p>
            ) : null}
          </div>
          {rp.seq && !receiptEntry && log?.kind === "report" ? (
            <p
              className={`rounded-xl border-2 p-3 text-sm font-semibold text-ink ${highlight && (!rp.hash || highlight.entry_hash === rp.hash) ? "border-success bg-success-soft" : "border-danger bg-danger-soft"}`}
              data-testid="receipt-highlight"
            >
              {highlight
                ? !rp.hash || highlight.entry_hash === rp.hash
                  ? t("audit.verify.highlightFound", { seq: rp.seq })
                  : t("audit.verify.hashDiffers")
                : t("audit.verify.highlightMissing", { seq: rp.seq })}
            </p>
          ) : null}
        </section>
      </main>
      <footer className="px-4 py-6 text-center text-sm text-muted">{t("common.footer")}</footer>
    </>
  );
}
