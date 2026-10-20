"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { demoLogin } from "@/lib/api/auth";
import { startSandbox } from "@/lib/api/demo";

export const JUDGE_EMAIL = "judge@demo.setu";

type Props = { label?: string; busyLabel?: string; withSandbox?: boolean };

export function JudgeModeButton({ label, busyLabel, withSandbox = false }: Props = {}) {
  const t = useT();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const start = async () => {
    setBusy(true);
    setFailed(false);
    try {
      if (withSandbox) await startSandbox();
      await demoLogin(JUDGE_EMAIL);
      router.push("/demo?judge=1");
    } catch {
      setFailed(true);
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-3">
      <Button variant="secondary" loading={busy} onClick={start}>
        {busy ? (busyLabel ?? t("landing.hero.judgeBusy")) : (label ?? t("landing.hero.judge"))}
      </Button>
      {failed ? (
        <Alert
          tone="danger"
          urgent
          title={t("landing.hero.judgeError")}
          action={
            <Button size="sm" variant="secondary" onClick={start}>
              {t("landing.hero.retry")}
            </Button>
          }
        />
      ) : null}
    </div>
  );
}
