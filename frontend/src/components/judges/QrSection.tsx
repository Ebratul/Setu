"use client";

import { useSyncExternalStore } from "react";

import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";

import { judgeConfig } from "./links";
import { QrCard } from "./QrCard";

/** Print only this block: everything else on the page is hidden by the @media print rule below. */
const PRINT_CSS = `@media print {
  body * { visibility: hidden !important; }
  #qr, #qr * { visibility: visible !important; }
  #qr { position: absolute; inset: 0 auto auto 0; width: 100%; background: #fff; color: #000; padding: 16px; }
  #qr .print-hide { display: none !important; }
  #qr .qr-card { break-inside: avoid; border: 1px solid #000; }
}`;

const subscribeNever = () => () => {};

export function QrSection() {
  const t = useT();
  const origin = useSyncExternalStore(
    subscribeNever,
    () => window.location.origin,
    () => "",
  );
  const base = judgeConfig().siteUrl ?? (origin || null);

  return (
    <section id="qr" aria-labelledby="qr-title" className="scroll-mt-20 py-10">
      <style>{PRINT_CSS}</style>
      <h2 id="qr-title" className="text-2xl font-bold tracking-tight text-ink">
        {t("judges.qr.title")}
      </h2>
      <p className="mt-2 max-w-3xl text-muted">{t("judges.qr.lead")}</p>
      {base ? (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <QrCard
            label={t("judges.qr.demo")}
            url={`${base}/demo`}
            slug="demo"
          />
          <QrCard
            label={t("judges.qr.judges")}
            url={`${base}/judges`}
            slug="judges"
          />
        </div>
      ) : null}
      <div className="print-hide mt-4 print:hidden">
        <Button variant="secondary" onClick={() => window.print()}>
          {t("judges.qr.print")}
        </Button>
      </div>
    </section>
  );
}
