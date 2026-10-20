"use client";

import { useT } from "@/i18n";

import { ButtonLink } from "./ButtonLink";
import { JudgeModeButton } from "./JudgeModeButton";

export function FinalCta() {
  const t = useT();
  return (
    <section id="demo" aria-labelledby="demo-title" className="scroll-mt-20 bg-brand-800 py-16 text-white">
      <div className="mx-auto w-full max-w-4xl px-4 text-center sm:px-6">
        <h2 id="demo-title" className="text-2xl font-bold sm:text-3xl">
          {t("landing.cta.title")}
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-base opacity-90">{t("landing.cta.sub")}</p>
        <div className="mt-8 flex flex-wrap items-start justify-center gap-3">
          <ButtonLink href="/demo" variant="accent">
            {t("landing.hero.guided")}
          </ButtonLink>
          <ButtonLink href="/login" variant="secondary">
            {t("landing.hero.own")}
          </ButtonLink>
          <JudgeModeButton />
        </div>
      </div>
    </section>
  );
}
