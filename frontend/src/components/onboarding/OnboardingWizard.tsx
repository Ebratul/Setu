"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/Button";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { Stepper } from "@/components/ui/Stepper";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { getOnboardingState, type OnboardingState } from "@/lib/api/onboarding";
import { signOutEverywhere } from "@/lib/auth/flow";
import {
  firstOpenStep,
  homeFor,
  isWizardStep,
  stepsFor,
  type WizardStep,
} from "@/lib/onboarding/steps";
import { useApi } from "@/lib/useApi";
import { markOnboardingSeen } from "@/lib/welcome";

import { BusinessStep } from "./steps/BusinessStep";
import { ContactStep } from "./steps/ContactStep";
import { DocumentsStep } from "./steps/DocumentsStep";
import { ReviewStep } from "./steps/ReviewStep";
import { RoleStep } from "./steps/RoleStep";
import { SecurityStep } from "./steps/SecurityStep";

export function OnboardingWizard() {
  const t = useT();
  const router = useRouter();
  const params = useSearchParams();
  const q = useApi((s) => getOnboardingState(s), "ob-state");
  const [local, setLocal] = useState<OnboardingState | null>(null);
  const [view, setView] = useState<WizardStep | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const first = useRef(true);
  const state = local ?? q.data ?? null;

  const unauth = q.error instanceof ApiError && q.error.status === 401;
  useEffect(() => {
    if (unauth) router.replace("/login?next=/onboarding");
  }, [unauth, router]);

  const role = state?.role;
  const status = state?.account_status;
  useEffect(() => {
    if (
      (role === "BUYER" || role === "SUPPLIER") &&
      status &&
      status !== "ACTIVE"
    )
      markOnboardingSeen();
  }, [role, status]);

  const home = state ? homeFor(state) : null;
  useEffect(() => {
    if (home) router.replace(home);
  }, [home, router]);

  const list = state ? stepsFor(state.role) : [];
  const wanted = params.get("step");
  const current: WizardStep | null = state
    ? (view ??
      (isWizardStep(wanted) && list.includes(wanted)
        ? wanted
        : firstOpenStep(state)))
    : null;

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    heading.current?.focus();
  }, [current]);

  async function refresh() {
    try {
      setLocal(await getOnboardingState());
    } catch {
      q.reload();
    }
  }

  if (q.error && !unauth) {
    return (
      <AuthShell title={t("ob.title")} neonOnly>
        <QueryError error={q.error} onRetry={q.reload} />
      </AuthShell>
    );
  }
  if (!state || current === null || home) {
    return (
      <AuthShell title={t("ob.title")} lead={t("ob.lead")} neonOnly>
        <Skeleton className="h-64" />
      </AuthShell>
    );
  }

  const idx = list.indexOf(current);
  const go = (s: WizardStep) => setView(s);
  const next = (updated?: OnboardingState) => {
    // The role step changes the step list (admins get fewer steps), so use the updated state.
    if (current === "role" && updated) return setView(firstOpenStep(updated));
    const n = list[idx + 1];
    if (n) setView(n);
    else router.replace("/onboarding/status");
  };
  const steps = list.map((s) => ({ id: s, label: t(`ob.step.${s}`) }));
  const common = { state, onState: setLocal, onNext: next };

  return (
    <AuthShell title={t("ob.title")} lead={t("ob.lead")} neonOnly>
      <div className="space-y-6">
        {state.change_requests.length > 0 ? (
          <p
            role="status"
            className="rounded-xl border border-warning bg-warning-soft p-3 text-sm text-ink"
          >
            {t("ob.changesBanner", { n: state.change_requests.length })}
          </p>
        ) : null}
        <Stepper steps={steps} current={idx} label={t("ob.steps")} />
        <section aria-labelledby="ob-step-h" className="space-y-4">
          <h2
            id="ob-step-h"
            ref={heading}
            tabIndex={-1}
            className="text-lg font-bold text-ink focus:outline-none"
          >
            {t("ob.stepOf", {
              n: idx + 1,
              total: list.length,
              name: t(`ob.step.${current}`),
            })}
          </h2>
          {current === "role" ? <RoleStep {...common} /> : null}
          {current === "contact" ? <ContactStep {...common} /> : null}
          {current === "business" ? <BusinessStep {...common} /> : null}
          {current === "documents" ? <DocumentsStep {...common} /> : null}
          {current === "security" ? (
            <SecurityStep {...common} onTotpDone={() => void refresh()} />
          ) : null}
          {current === "review" ? <ReviewStep {...common} onEdit={go} /> : null}
        </section>
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
          {idx > 0 ? (
            <Button variant="secondary" onClick={() => setView(list[idx - 1])}>
              {t("ob.back")}
            </Button>
          ) : null}
          <Button
            variant="ghost"
            onClick={async () => {
              await signOutEverywhere();
              router.replace("/login");
            }}
          >
            {t("auth.status.signOut")}
          </Button>
        </div>
      </div>
    </AuthShell>
  );
}
