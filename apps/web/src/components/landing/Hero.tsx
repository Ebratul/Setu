"use client";

import { useT } from "@/i18n";

import { ButtonLink } from "./ButtonLink";
import { HeroPreview } from "./HeroPreview";
import { JudgeModeButton } from "./JudgeModeButton";

export function Hero() {
  const t = useT();
  return (
    <section aria-labelledby="hero-title" className="bg-brand-50">
      <div className="mx-auto grid w-full max-w-6xl items-center gap-10 px-4 py-12 sm:px-6 sm:py-16 lg:grid-cols-2 lg:py-24">
        <div className="min-w-0">
          <p className="text-sm font-semibold tracking-wide text-brand-text uppercase">
            {t("landing.hero.eyebrow")}
          </p>
          <h1 id="hero-title" className="mt-3 text-display font-extrabold tracking-tight text-ink">
            {t("landing.hero.title")}
          </h1>
          <p className="mt-5 max-w-xl text-lg text-muted">{t("landing.hero.sub")}</p>
          <div className="mt-8 flex flex-wrap items-start gap-3">
            <ButtonLink href="/demo" variant="accent">
              {t("landing.hero.guided")}
            </ButtonLink>
            <ButtonLink href="/login" variant="primary">
              {t("landing.hero.own")}
            </ButtonLink>
            <JudgeModeButton />
          </div>
        </div>
        <HeroPreview />
      </div>
    </section>
  );
}
