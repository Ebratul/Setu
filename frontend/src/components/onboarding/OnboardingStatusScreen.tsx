"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthShell, authLinkClass } from "@/components/auth/AuthShell";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { hasKey, useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { getOnboardingState } from "@/lib/api/onboarding";
import { signOutEverywhere } from "@/lib/auth/flow";
import { isDocTarget, stepForTarget } from "@/lib/onboarding/changes";
import { labelKey } from "@/lib/onboarding/errors";
import { homeFor, stepDone, stepsFor } from "@/lib/onboarding/steps";
import { useApi } from "@/lib/useApi";
import { markOnboardingSeen } from "@/lib/welcome";

import { CheckStatusBadge } from "./CheckStatusBadge";

export const STATUS_POLL_MS = 20_000;

export function OnboardingStatusScreen() {
  const t = useT();
  const router = useRouter();
  const q = useApi((signal) => getOnboardingState(signal), "onboarding-state");
  const { reload } = q;
  const state = q.data ?? null;
  const [busy, setBusy] = useState(false);

  const err = q.error;
  const unauth = err instanceof ApiError && err.status === 401;
  const changes =
    state?.decision === "CHANGES_REQUESTED" ||
    (state?.change_requests.length ?? 0) > 0;
  const needsProfile =
    state !== null &&
    (state.account_status === null ||
      state.account_status === "PENDING_PROFILE") &&
    !changes;
  const home = state && !changes ? homeFor(state) : null;
  const redirect = unauth
    ? "/login?next=/onboarding/status"
    : needsProfile
      ? "/onboarding"
      : home && home !== "/onboarding/status"
        ? home
        : null;

  useEffect(() => {
    if (redirect) router.replace(redirect);
  }, [redirect, router]);

  const waiting =
    state !== null &&
    !changes &&
    state.account_status === "PENDING_VERIFICATION";
  useEffect(() => {
    if (!waiting) return;
    const tick = () => {
      if (document.visibilityState === "visible") reload();
    };
    const id = setInterval(tick, STATUS_POLL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [waiting, reload]);

  useEffect(() => {
    if (state && state.account_status && state.account_status !== "ACTIVE")
      markOnboardingSeen();
  }, [state]);

  async function onSignOut() {
    setBusy(true);
    await signOutEverywhere();
    router.replace("/login");
  }

  const failed = err !== undefined && !unauth;
  const checks = (state?.checks ?? []).filter(
    (c) => !c.code.toUpperCase().includes("SANCTION"),
  );
  const stepsList = state
    ? stepsFor(state.role).filter((s) => s !== "role" && s !== "review")
    : [];

  return (
    <AuthShell title={t("ost.title")} neonOnly>
      <div className="space-y-5">
        {failed ? (
          <Alert
            tone="danger"
            urgent
            action={
              <Button size="sm" onClick={reload}>
                {t("common.retry")}
              </Button>
            }
          >
            {t("ost.loadFailed")}
          </Alert>
        ) : null}
        {state === null && !failed ? (
          <p role="status">{t("common.loading")}</p>
        ) : null}
        {state && !redirect ? (
          <>
            <div aria-live="polite">
              {changes ? (
                <Alert tone="warning" title={t("ost.changes.title")}>
                  {t("ost.changes.body")}
                </Alert>
              ) : (
                <Alert tone="warning" title={t("ost.pending.title")}>
                  {t("ost.pending.body")}
                </Alert>
              )}
            </div>

            {changes && state.change_requests.length > 0 ? (
              <section aria-labelledby="ost-changes-h" className="space-y-2">
                <h2 id="ost-changes-h" className="text-lg font-bold text-ink">
                  {t("ost.changes.list")}
                </h2>
                <ul className="divide-y divide-line rounded-card border border-line bg-surface">
                  {state.change_requests.map((c) => {
                    const step = stepForTarget(c.target);
                    const name = isDocTarget(c.target)
                      ? t(`ob.doc.${c.target}`)
                      : hasKey(`ob.f.${labelKey(c.target)}`)
                        ? t(`ob.f.${labelKey(c.target)}`)
                        : c.target;
                    return (
                      <li
                        key={`${c.target}-${c.note}`}
                        className="flex flex-wrap items-start justify-between gap-3 px-4 py-3 text-sm"
                      >
                        <div className="min-w-0">
                          <p className="font-semibold text-ink">{name}</p>
                          <p className="break-words text-muted">{c.note}</p>
                        </div>
                        <Link
                          href={`/onboarding?step=${step}`}
                          className={authLinkClass}
                          aria-label={`${t("ost.fix")}: ${name}`}
                        >
                          {t("ost.fix")}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
                <Link
                  href="/onboarding?step=review"
                  className={`${authLinkClass} text-base`}
                >
                  {t("ost.resubmit")}
                </Link>
              </section>
            ) : null}

            <section aria-labelledby="ost-list-h" className="space-y-2">
              <h2 id="ost-list-h" className="text-lg font-bold text-ink">
                {t("ost.checklist")}
              </h2>
              <ul className="divide-y divide-line rounded-card border border-line bg-surface">
                {stepsList.map((s) => {
                  const done = stepDone(state, s);
                  return (
                    <li
                      key={s}
                      className="flex items-center justify-between gap-2 px-4 py-3 text-sm"
                    >
                      <span className="text-ink">{t(`ob.step.${s}`)}</span>
                      <span
                        className={`inline-flex items-center gap-1 font-semibold ${done ? "text-success" : "text-warning"}`}
                      >
                        <Icon name={done ? "check" : "clock"} size={14} />
                        {done ? t("ost.done") : t("ost.todo")}
                      </span>
                    </li>
                  );
                })}
                <li className="flex items-center justify-between gap-2 px-4 py-3 text-sm">
                  <span className="text-ink">{t("ost.humanReview")}</span>
                  <span className="inline-flex items-center gap-1 font-semibold text-warning">
                    <Icon name="clock" size={14} />
                    {t("ost.inProgress")}
                  </span>
                </li>
              </ul>
            </section>

            {checks.length > 0 ? (
              <section aria-labelledby="ost-checks-h" className="space-y-2">
                <h2 id="ost-checks-h" className="text-lg font-bold text-ink">
                  {t("onb.st.checks")}
                </h2>
                <ul className="divide-y divide-line rounded-card border border-line bg-surface">
                  {checks.map((c) => (
                    <li
                      key={c.code}
                      className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm"
                    >
                      <span className="text-ink">
                        {hasKey(`onb.check.${c.code}`)
                          ? t(`onb.check.${c.code}`)
                          : c.code}
                      </span>
                      <CheckStatusBadge status={c.status} />
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {waiting ? (
              <p className="text-xs text-muted">{t("onb.st.polling")}</p>
            ) : null}
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
