"use client";

import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { downloadHref } from "@/lib/qr";

type Props = { codes: string[]; onConfirmed: () => void };

/** One-time recovery codes; the user must confirm they saved them before continuing. */
export function RecoveryCodes({ codes, onConfirmed }: Props) {
  const t = useT();
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="space-y-4">
      <Alert tone="warning" title={t("tp.codes.title")}>
        {t("tp.codes.body")}
      </Alert>
      <ul className="grid grid-cols-2 gap-2 rounded-card border border-line bg-surface-alt p-4 font-mono text-sm text-ink" aria-label={t("tp.codes.title")}>
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => void copy()}>
          {copied ? t("tp.codes.copied") : t("tp.codes.copy")}
        </Button>
        <Button
          variant="secondary"
          onClick={() => downloadHref(`data:text/plain;charset=utf-8,${encodeURIComponent(text)}`, "setu-recovery-codes.txt")}
        >
          {t("tp.codes.download")}
        </Button>
      </div>
      <label className="flex min-h-11 items-start gap-3 text-sm text-ink">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} className="mt-1 size-4" />
        <span>{t("tp.codes.confirm")}</span>
      </label>
      <Button onClick={onConfirmed} disabled={!saved}>
        {t("tp.codes.done")}
      </Button>
    </div>
  );
}
