"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AuthShell } from "@/components/auth/AuthShell";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { hasKey, useT } from "@/i18n";
import { startSession } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { getOnboardingStatus } from "@/lib/api/onboarding";
import { useApi } from "@/lib/useApi";
import { safeNext, signOutEverywhere } from "@/lib/auth/flow";

import { CheckStatusBadge } from "./CheckStatusBadge";

export const STATUS_POLL_MS = 20_000;

export function OnboardingStatusScreen() {
  const t = useT();
  const router = useRouter();
  const q = useApi((signal) => getOnboardingStatus(signal), "onboarding-status");
  const { reload } = q;
  const state = q.data ?? null;
  const [activateFailed, setActivateFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const activating = useRef(false);

  const done = state !== null && state.status !== "PENDING";
  const err = q.error;
  const redirect =
    err instanceof ApiError && err.status === 401
      ? "/login?next=/onboarding/status"
      : err instanceof ApiError && err.code === "NOT_ONBOARDED"
        ? "/onboarding"
        : null;
  const failed = err !== undefined && redirect === null;

  useEffect(() => {
    if (redirect) router.replace(redirect);
  }, [redirect, router]);

  useEffect(() => {
    if (done) return;
    const tick = () => {
      if (document.visibilityState === "visible") reload();
    };
    const id = setInterval(tick, STATUS_POLL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [done, reload]);

  const activate = useCallback(() => {
    if (activating.current) return;
    activating.current = true;
    startSession().then(
      (user) => router.replace(safeNext(null, user.role)),
      () => {
        activating.current = false;
        setActivateFailed(true);
      },
    );
  }, [router]);

  useEffect(() => {
    if (state?.status === "APPROVED" && state.account_status === "ACTIVE") activate();
    else if (state?.status === "REJECTED") router.replace("/account-status?reason=suspended");
  }, [state, activate, router]);

  async function onSignOut() {
    setBusy(true);
    await signOutEverywhere();
    router.replace("/login");
  }

  const checks = (state?.checks ?? []).filter((c) => !c.code.toUpperCase().includes("SANCTION"));

  return (
    <AuthShell title={t("onb.st.title")} neonOnly>
      <div className="space-y-5">
        {failed ? (
          <Alert tone="danger" urgent action={<Button size="sm" onClick={reload}>{t("common.retry")}</Button>}>
            {t("onb.st.loadFailed")}
          </Alert>
        ) : null}
        {state === null && !failed ? <p role="status">{t("common.loading")}</p> : null}
        {state ? (
          <>
            <div aria-live="polite">
              {state.status === "APPROVED" ? (
                <Alert tone="success" title={t("onb.st.approved.title")}>
                  {t("onb.st.approved.body")}
                </Alert>
              ) : (
                <Alert tone="warning" title={t("onb.st.pending.title")}>
                  {t("onb.st.pending.body")}
                </Alert>
              )}
            </div>
            {activateFailed ? (
              <Alert tone="danger" urgent action={<Button size="sm" onClick={() => { setActivateFailed(false); activate(); }}>{t("common.retry")}</Button>}>
                {t("onb.st.activateFailed")}
              </Alert>
            ) : null}
            {state.party_name ? (
              <p className="text-sm text-muted">
                {t("onb.st.company")}: <span className="font-semibold text-ink">{state.party_name}</span>
              </p>
            ) : null}
            {checks.length > 0 ? (
              <section aria-labelledby="onb-checks-h" className="space-y-2">
                <h2 id="onb-checks-h" className="text-lg font-bold text-ink">
                  {t("onb.st.checks")}
                </h2>
                <ul className="divide-y divide-line rounded-card border border-line bg-surface">
                  {checks.map((c) => (
                    <li key={c.code} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                      <span className="text-ink">{hasKey(`onb.check.${c.code}`) ? t(`onb.check.${c.code}`) : c.code}</span>
                      <CheckStatusBadge status={c.status} />
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {!done ? <p className="text-xs text-muted">{t("onb.st.polling")}</p> : null}
          </>
        ) : null}
        <div>
          <Button variant="secondary" onClick={onSignOut} loading={busy}>
            {t("auth.status.signOut")}
          </Button>
        </div>
      </div>
    </AuthShell>
  );
}
