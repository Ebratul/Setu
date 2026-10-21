"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import { getCreditRecord, verifyCreditRecord, type CreditRecord } from "@/lib/api/creditRecords";
import { formatDate, formatMoney, type Currency } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const str = (v: unknown) => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "—");
const short = (s: string, head = 18, tail = 10) => (s.length > head + tail + 1 ? `${s.slice(0, head)}…${s.slice(-tail)}` : s);
const CURRENCIES = ["USD", "BDT", "CNY"];

/** Signed credit record of a completed deal: key facts, hash, signature and an on-demand re-verification. */
export function CreditRecordCard({ reference }: { reference: string }) {
  const t = useT();
  const rec = useApi((s) => getCreditRecord(reference, s), `credit-record|${reference}`);
  return (
    <div data-demo="credit-record">
      <Card as="section" labelledBy="crec-h" className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="crec-h" className="text-lg font-bold text-ink">
            {t("crec.title")}
          </h2>
          <SimulatedBadge />
        </div>
        {rec.error ? (
          <QueryError error={rec.error} onRetry={rec.reload} />
        ) : rec.loading ? (
          <p role="status" className="text-sm text-muted">
            {t("common.loading")}
          </p>
        ) : !rec.data ? (
          <p className="text-sm text-muted">{t("crec.none")}</p>
        ) : (
          <RecordBody record={rec.data} />
        )}
      </Card>
    </div>
  );
}

function RecordBody({ record }: { record: CreditRecord }) {
  const t = useT();
  const { lang } = useLang();
  const p = record.payload;
  const cur = str(p.currency);
  const amount = typeof p.amount === "string" && CURRENCIES.includes(cur) ? formatMoney(p.amount, cur as Currency, lang) : str(p.amount);
  const evidence = Array.isArray(p.evidence) ? p.evidence.length : 0;
  const [check, setCheck] = useState<{ verified: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const verified = check ? check.verified : record.verified;

  async function again() {
    setBusy(true);
    setFailed(false);
    try {
      setCheck(await verifyCreditRecord(record.payload, record.signature));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(record.signature);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const facts: [string, string][] = [
    [t("crec.buyer"), str(p.buyer)],
    [t("crec.supplier"), str(p.supplier)],
    [t("crec.amount"), amount],
    [t("crec.onTime"), p.on_time === true ? t("crec.yes") : p.on_time === false ? t("crec.no") : "—"],
    [t("crec.disputes"), str(p.disputes)],
    [t("crec.evidence"), String(evidence)],
    [t("crec.completed"), typeof p.completed_on === "string" ? formatDate(p.completed_on, lang) : "—"],
  ];

  return (
    <>
      <div aria-live="polite" className="flex flex-wrap items-center gap-2" data-testid="crec-status">
        {verified ? (
          <Badge tone="success" icon={<Icon name="shield" size={12} />}>
            {t("crec.verified")}
          </Badge>
        ) : (
          <Badge tone="danger">{t("crec.notVerified")}</Badge>
        )}
        <span className="text-xs text-muted">
          {t("crec.hashOk")}: {record.hash_ok ? "✓" : "✗"} · {t("crec.sigOk")}: {record.signature_ok ? "✓" : "✗"}
        </span>
      </div>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        {facts.map(([k, v]) => (
          <div key={k} className="min-w-0">
            <dt className="text-muted">{k}</dt>
            <dd className="font-semibold break-words text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      <dl className="space-y-2 rounded-xl bg-surface-alt p-3 text-xs">
        <div>
          <dt className="font-semibold text-muted">{t("crec.hash")}</dt>
          <dd className="font-mono break-all text-ink" data-testid="crec-hash">
            {record.payload_hash}
          </dd>
        </div>
        <div>
          <dt className="font-semibold text-muted">{t("crec.signature")}</dt>
          <dd className="flex flex-wrap items-center gap-2">
            <code className="font-mono text-ink" title={record.signature} data-testid="crec-signature">
              {short(record.signature)}
            </code>
            <Button size="sm" variant="secondary" onClick={() => void copy()}>
              {copied ? t("crec.copied") : t("crec.copy")}
            </Button>
          </dd>
        </div>
        <div>
          <dt className="font-semibold text-muted">{t("crec.keyId")}</dt>
          <dd className="font-mono text-ink">{record.key_id}</dd>
        </div>
      </dl>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => void again()} loading={busy}>
          {t("crec.verifyAgain")}
        </Button>
        {failed ? (
          <p role="alert" className="text-sm font-medium text-danger">
            {t("crec.verifyFailed")}
          </p>
        ) : null}
      </div>
    </>
  );
}
