"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { resolveSignedIn, signOutEverywhere } from "@/lib/auth/flow";
import { useAuthMode } from "@/lib/auth/useAuthMode";

import { AuthShell, authLinkClass } from "./AuthShell";
import { GoogleButton } from "./GoogleButton";
import { LoginPanel } from "./LoginPanel";
import { SignInForm } from "./SignInForm";

function LegalLinks() {
  const t = useT();
  const { lang } = useLang();
  return (
    <nav
      aria-label={t("lg.legalNav")}
      className="flex flex-wrap gap-x-5 border-t border-line pt-4 text-sm"
    >
      <Link
        href={`/docs/${lang === "bn" ? "bn" : "en"}/security/why-we-ask`}
        className={authLinkClass}
      >
        {t("lg.why")}
      </Link>
      <Link href="/terms" className={authLinkClass}>
        {t("lg.terms")}
      </Link>
      <Link href="/privacy" className={authLinkClass}>
        {t("lg.privacy")}
      </Link>
    </nav>
  );
}

function LoginBody() {
  const t = useT();
  const router = useRouter();
  const params = useSearchParams();
  const { config } = useAuthMode();
  const [errorKey, setErrorKey] = useState("");
  const returning = params.get("oauth") === "1" && config?.mode === "neon";
  const [finishing, setFinishing] = useState(returning);
  const started = useRef(false);
  const next = params.get("next");

  useEffect(() => {
    if (!returning || started.current) return;
    started.current = true;
    void (async () => {
      const result = await resolveSignedIn(next);
      if (result.kind === "go") {
        router.replace(result.path);
        return;
      }
      await signOutEverywhere();
      setErrorKey(result.key);
      setFinishing(false);
    })();
  }, [returning, next, router]);

  if (config === null) return <Skeleton className="h-40" />;
  const neon = config.mode === "neon";

  return (
    <div className="space-y-6">
      <div aria-live="polite">
        {finishing ? (
          <p role="status" className="text-sm text-muted">
            {t("lg.finishing")}
          </p>
        ) : null}
        {errorKey ? (
          <p role="alert" className="text-sm font-medium text-danger">
            {t(errorKey)}
          </p>
        ) : null}
      </div>
      {neon && config.googleEnabled ? (
        <div className="space-y-3">
          <GoogleButton
            next={next}
            onError={setErrorKey}
            disabled={finishing}
          />
          <p className="text-center text-xs text-muted">{t("lg.googleNote")}</p>
        </div>
      ) : null}
      {neon ? (
        <section aria-labelledby="lg-email-h" className="space-y-3">
          <h2 id="lg-email-h" className="text-sm font-semibold text-muted">
            {config.googleEnabled ? t("lg.orEmail") : t("lg.email")}
          </h2>
          <SignInForm />
        </section>
      ) : null}
      {config.demoEnabled ? (
        <section aria-labelledby="lg-demo-h" className="space-y-3">
          <h2 id="lg-demo-h" className="text-lg font-bold text-ink">
            {t("lg.demoTitle")}
          </h2>
          <Alert tone="warning">
            <span role="note">{t("login.demoOnly")}</span>
          </Alert>
          <LoginPanel />
        </section>
      ) : null}
      {!neon && !config.demoEnabled ? (
        <Alert tone="info">{t("lg.nothing")}</Alert>
      ) : null}
      <LegalLinks />
    </div>
  );
}

export function LoginScreen() {
  const t = useT();
  const { mode } = useAuthMode();
  return (
    <AuthShell
      title={mode === "neon" ? t("auth.signIn.title") : t("login.title")}
      lead={t("auth.signIn.lead")}
    >
      <Suspense fallback={<Skeleton className="h-40" />}>
        <LoginBody />
      </Suspense>
    </AuthShell>
  );
}
