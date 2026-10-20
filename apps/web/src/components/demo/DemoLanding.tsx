"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ButtonLink } from "@/components/landing/ButtonLink";
import { DemoHub } from "@/components/landing/DemoHub";
import { PublicFooter } from "@/components/landing/PublicFooter";
import { PublicHeader } from "@/components/landing/PublicHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import { demoLogin } from "@/lib/api/auth";
import { demoErrorKind, getPreflight, startSandbox } from "@/lib/api/demo";
import type { EvalResults } from "@/lib/evalResults";
import { useApi } from "@/lib/useApi";

import { biText, toDemoLang } from "./demoModel";

/** Query params that carry over when `/demo?step=N` redirects to the run screen. */
export function runHref(params: URLSearchParams): string | null {
  const step = params.get("step");
  if (!step || !/^\d+$/.test(step)) return null;
  const out = new URLSearchParams({ step });
  for (const k of ["mode", "play", "lang"]) {
    const v = params.get(k);
    if (v) out.set(k, v);
  }
  return `/demo/run?${out.toString()}`;
}

export function DemoLanding({ results }: { results: EvalResults | null }) {
  const t = useT();
  const router = useRouter();
  const params = useSearchParams();
  const { lang } = useLang();
  const dl = toDemoLang(lang);
  const redirect = runHref(params);
  const pre = useApi((s) => getPreflight(s), "preflight", !redirect);
  const [busy, setBusy] = useState<"watch" | "own" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (redirect) router.replace(redirect);
  }, [redirect, router]);

  if (redirect) {
    return (
      <main id="main" className="flex min-h-dvh items-center justify-center p-6">
        <h1 className="sr-only">{t("demo.title")}</h1>
        <p role="status" className="text-muted">
          {t("demo.starting")}
        </p>
      </main>
    );
  }

  async function begin(kind: "watch" | "own") {
    setBusy(kind);
    setError(null);
    try {
      await startSandbox();
      if (kind === "own") await demoLogin("rahima@demo.setu");
      router.push(kind === "watch" ? "/demo/run?play=1" : "/app");
    } catch (e) {
      const k = demoErrorKind(e);
      setError(t(`demo.err.${k === "other" || k === "required" ? "network" : k}`, { s: 5 }));
      setBusy(null);
    }
  }

  const items = pre.data?.items ?? [];
  const allOk = pre.data?.ok === true;

  return (
    <>
      <PublicHeader />
      <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-4 py-10 sm:px-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-extrabold tracking-tight text-ink">{t("demo.landing.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="mt-3 text-base text-ink">{t("demo.landing.intro")}</p>
        <p className="mt-2 text-sm text-muted">{t("demo.landing.sandboxNote")}</p>

        <div className="mt-6 flex flex-wrap gap-3">
          <Button variant="accent" onClick={() => void begin("watch")} loading={busy === "watch"} disabled={busy !== null}>
            <Icon name="play" size={14} />
            {t("demo.landing.watch")}
          </Button>
          <Button variant="primary" onClick={() => void begin("own")} loading={busy === "own"} disabled={busy !== null}>
            {t("demo.landing.own")}
          </Button>
          <ButtonLink href="/demo/run?mode=presenter" variant="secondary">
            {t("demo.landing.presenter")}
          </ButtonLink>
        </div>
        <p className="mt-2 text-xs text-muted">{t("demo.landing.hint")}</p>
        {error ? (
          <p role="alert" className="mt-3 rounded-xl border border-danger bg-danger-soft p-3 text-sm font-medium text-danger">
            {error}
          </p>
        ) : null}

        <Card as="section" labelledBy="preflight-h" className="mt-8">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="preflight-h" className="text-lg font-bold text-ink">
              {t("demo.preflight.title")}
            </h2>
            <Button variant="secondary" size="sm" onClick={pre.reload} loading={pre.loading && pre.data !== undefined}>
              {t("demo.preflight.refresh")}
            </Button>
          </div>
          <div aria-live="polite" className="min-h-48">
            {pre.error ? (
              <p role="alert" className="mt-3 text-sm font-medium text-danger">
                {t("demo.preflight.unreachable")}
              </p>
            ) : pre.data ? (
              <>
                <p className={`mt-2 text-sm font-semibold ${allOk ? "text-success" : "text-danger"}`} data-testid="preflight-summary">
                  {allOk ? t("demo.preflight.allOk") : t("demo.preflight.someFail")}
                  {pre.data.replay ? ` · ${t("demo.preflight.replay")}` : ""}
                </p>
                <ul className="mt-2 space-y-1" data-testid="preflight-list">
                  {items.map((i) => (
                    <li key={i.id} data-ok={i.ok} className="flex items-start gap-2 text-sm text-ink">
                      <Icon name={i.ok ? "check" : "x"} size={16} className={`mt-0.5 shrink-0 ${i.ok ? "text-success" : "text-danger"}`} />
                      <span>
                        <span className="sr-only">{i.ok ? t("demo.preflight.ok") : t("demo.preflight.fail")}: </span>
                        <span className="font-semibold">{biText(i.label, dl)}</span>
                        {i.detail ? <span className="text-muted"> – {i.detail}</span> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p role="status" className="mt-3 text-sm text-muted">
                {t("common.loading")}
              </p>
            )}
          </div>
        </Card>
        <DemoHub results={results} embedded />
      </main>
      <PublicFooter />
    </>
  );
}
