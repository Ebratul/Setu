"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { verifySupplier, type KybResult } from "@/lib/api/kyb";

type Props = { supplierId: string; onDone: (r: KybResult) => void };

export function RerunButton({ supplierId, onDone }: Props) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function run() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await verifySupplier(supplierId);
      onDone(r);
      setMsg({ ok: true, text: t("sup.rerunDone") });
    } catch (e) {
      const forbidden = e instanceof ApiError && e.status === 403;
      setMsg({
        ok: false,
        text: t(forbidden ? "sup.rerunForbidden" : "sup.rerunFailed"),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1">
      <Button onClick={run} disabled={busy} aria-busy={busy}>
        {busy ? t("sup.rerunning") : t("sup.rerun")}
      </Button>
      <p
        role={msg && !msg.ok ? "alert" : "status"}
        aria-live="polite"
        className={`text-sm ${msg?.ok === false ? "text-danger" : "text-muted"}`}
      >
        {msg?.text}
      </p>
    </div>
  );
}
