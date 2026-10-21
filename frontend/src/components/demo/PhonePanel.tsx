"use client";

import { useCallback, useEffect, useState } from "react";

import { useT } from "@/i18n";
import { getDemoPhone, type PhoneMessage } from "@/lib/api/approvals";
import { usePoll } from "@/lib/usePoll";

/** Simulated SMS inbox inside the demo panel, so OTP codes are always visible to the audience. */
export function PhonePanel({ active }: { active: boolean }) {
  const t = useT();
  const [msgs, setMsgs] = useState<PhoneMessage[] | null>(null);
  const refresh = useCallback(async () => {
    try {
      setMsgs(await getDemoPhone());
    } catch {
      /* keep last state */
    }
  }, []);
  useEffect(() => {
    if (!active) return;
    const id = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(id);
  }, [active, refresh]);
  usePoll(() => void refresh(), 2500, active);

  const newest = msgs?.[0];
  return (
    <section aria-labelledby="demo-phone-h" data-testid="demo-phone-panel" className="rounded-[1.5rem] border-2 border-ink bg-surface p-3">
      <h2 id="demo-phone-h" className="text-sm font-bold text-ink">
        <span aria-hidden="true">📱 </span>
        {t("demo.phone.title")}
      </h2>
      <p className="text-xs font-semibold tracking-wide text-warning uppercase">{t("phone.simulated")}</p>
      <div aria-live="polite" className="mt-2 rounded-2xl bg-surface-alt p-2 text-sm text-ink">
        {newest ? (
          <>
            <p className="break-words">{newest.body}</p>
            <p className="mt-1 text-center">
              <span className="sr-only">{t("phone.newMessage")}: </span>
              <strong data-testid="demo-sms-code" className="font-mono text-2xl tracking-widest">
                {newest.code}
              </strong>
            </p>
          </>
        ) : (
          <p className="text-xs text-muted">{msgs === null ? t("demo.phone.unavailable") : t("phone.empty")}</p>
        )}
      </div>
    </section>
  );
}
