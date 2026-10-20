"use client";

import QRCode from "qrcode";
import { useEffect, useState } from "react";

import { CopyChip } from "@/components/approvals/CopyChip";
import { TierBadge } from "@/components/risk/TierBadge";
import { Button } from "@/components/ui/Button";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getAuditEntry, type AuditEntryDetail } from "@/lib/api/audit";
import { receiptUrl } from "@/lib/audit/receipt";
import type { AuditLine } from "@/lib/audit/verify";
import { formatMoney, type Currency } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { fmtTime, shortHash } from "./auditText";

const CURRENCIES = ["USD", "BDT", "CNY"];

function amountText(e: AuditEntryDetail, lang: "en" | "bn" | "zh"): string | null {
  const amount = e.payload.amount;
  if (typeof amount !== "string") return null;
  const cur = e.payload.currency;
  if (typeof cur === "string" && CURRENCIES.includes(cur)) return formatMoney(amount, cur as Currency, lang === "bn" ? "bn" : "en");
  return typeof cur === "string" ? `${amount} ${cur}` : amount;
}

function token(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("image"));
    img.src = src;
  });
}

type Row = { label: string; value: string };

async function renderPng(rows: Row[], title: string, simulated: string, qr: string): Promise<Blob | null> {
  const W = 720;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = 220 + rows.length * 44 + 340;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.fillStyle = token("--color-surface", "white");
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = token("--color-ink", "black");
  ctx.font = "700 32px sans-serif";
  ctx.fillText(title, 32, 60);
  ctx.fillStyle = token("--color-warning", "black");
  ctx.font = "700 20px sans-serif";
  ctx.fillText(simulated.toUpperCase(), 32, 100);
  let y = 150;
  for (const r of rows) {
    ctx.fillStyle = token("--color-muted", "gray");
    ctx.font = "16px sans-serif";
    ctx.fillText(r.label, 32, y);
    ctx.fillStyle = token("--color-ink", "black");
    ctx.font = "600 18px monospace";
    ctx.fillText(r.value, 260, y);
    y += 44;
  }
  ctx.drawImage(await loadImage(qr), 32, y + 10, 300, 300);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
}

export function ReceiptBody({ seq }: { seq: number }) {
  const t = useT();
  const { lang } = useLang();
  const q = useApi((s) => getAuditEntry(seq, s), `receipt|${seq}`);
  const [qr, setQr] = useState<string | null>(null);
  const entry = q.data;
  const url = entry ? receiptUrl(entry as unknown as AuditLine, window.location.origin) : null;

  useEffect(() => {
    if (!url) return;
    let live = true;
    QRCode.toDataURL(url, { errorCorrectionLevel: "L", margin: 2, width: 320 }).then(
      (d) => live && setQr(d),
      () => live && setQr(null),
    );
    return () => {
      live = false;
    };
  }, [url]);

  if (q.error) return <QueryError error={q.error} onRetry={q.reload} />;
  if (!entry || !url) return <Skeleton className="h-64" />;

  const ref = ["deal_ref", "deal_reference", "reference"].map((k) => entry.payload[k]).find((v) => typeof v === "string") as string | undefined;
  const amount = amountText(entry, lang);
  const sig = `${entry.signature.slice(0, 16)}…${entry.signature.slice(-8)}`;
  const rows: Row[] = [
    { label: t("audit.receipt.deal"), value: ref ?? entry.deal_id ?? "—" },
    ...(amount ? [{ label: t("audit.receipt.amount"), value: amount }] : []),
    { label: t("audit.receipt.tier"), value: t("risk.tier." + Math.min(Math.max(entry.tier, 0), 3)) },
    { label: t("audit.receipt.approver"), value: entry.actor_id },
    { label: t("audit.receipt.time"), value: fmtTime(entry.ts, lang) },
    { label: t("audit.receipt.seq"), value: `#${entry.seq}` },
    { label: t("audit.receipt.hash"), value: shortHash(entry.entry_hash, 16) + "…" },
    { label: t("audit.receipt.signature"), value: sig },
  ];

  async function download() {
    if (!qr) return;
    const blob = await renderPng(rows, t("audit.receipt.title"), t("common.simulated"), qr);
    if (!blob) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `setu-receipt-${entry?.seq}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  return (
    <div className="space-y-4">
      <div className="receipt-print space-y-3" data-testid="receipt">
        <div className="flex flex-wrap items-center gap-2">
          <SimulatedBadge />
          <TierBadge tier={entry.tier} decision={entry.decision} />
        </div>
        <p className="text-sm text-ink">{lang === "bn" ? entry.text_bn : entry.text_en}</p>
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
          {rows.map((r) => (
            <div key={r.label} className="contents">
              <dt className="text-muted">{r.label}</dt>
              <dd className="font-semibold break-all text-ink">{r.value}</dd>
            </div>
          ))}
        </dl>
        <div className="flex flex-wrap items-center gap-4">
          {qr ? (
            // eslint-disable-next-line @next/next/no-img-element -- generated data URL
            <img src={qr} alt={t("audit.receipt.qrAlt")} width={160} height={160} className="rounded-xl border border-line" />
          ) : (
            <Skeleton className="size-40" />
          )}
          <p className="max-w-xs text-xs text-muted">{t("audit.receipt.qrHelp")}</p>
        </div>
      </div>
      <div className="no-print flex flex-wrap gap-2">
        <CopyChip
          text={shortHash(entry.entry_hash, 12)}
          copyValue={entry.entry_hash}
          ariaLabel={t("audit.receipt.copyHash")}
          copiedLabel={t("audit.copied")}
        />
        <CopyChip
          text={sig}
          copyValue={entry.signature}
          ariaLabel={t("audit.receipt.copySig")}
          copiedLabel={t("audit.copied")}
        />
      </div>
      <div className="no-print flex flex-wrap gap-2">
        <Button onClick={() => void download()} disabled={!qr}>
          {t("audit.receipt.png")}
        </Button>
        <Button variant="secondary" onClick={() => window.print()}>
          {t("audit.receipt.pdf")}
        </Button>
        <a
          href={url}
          target="_blank"
          rel="noopener"
          className="inline-flex items-center rounded-xl px-4 py-2 text-sm font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {t("audit.receipt.open")}
        </a>
      </div>
    </div>
  );
}
