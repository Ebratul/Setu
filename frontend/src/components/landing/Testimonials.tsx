"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";

import { Section } from "./Section";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

const PERSONAS = ["rahima", "lin", "officer"] as const;
export const SLIDE_MS = 7000;

const ctl =
  "flex size-11 items-center justify-center rounded-xl border border-line text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function Testimonials() {
  const t = useT();
  const reduced = usePrefersReducedMotion();
  const [index, setIndex] = useState(0);
  const [userPaused, setUserPaused] = useState(false);
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const total = PERSONAS.length;
  const auto = !reduced && !userPaused && !hover && !focus;

  useEffect(() => {
    if (!auto) return;
    const id = setInterval(() => setIndex((i) => (i + 1) % total), SLIDE_MS);
    return () => clearInterval(id);
  }, [auto, total]);

  return (
    <Section id="voices" title={t("landing.voices.title")} lead={t("landing.voices.lead")} alt>
      <div
        role="region"
        aria-roledescription="carousel"
        aria-label={t("landing.voices.title")}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
      >
        <div className="mb-4">
          <Badge tone="info">{t("landing.voices.badge")}</Badge>
        </div>
        <div aria-live={auto ? "off" : "polite"}>
          {PERSONAS.map((p, i) => (
            <figure
              key={p}
              role="group"
              aria-roledescription="slide"
              aria-label={t("landing.voices.slide", { n: i + 1, total })}
              hidden={i !== index}
              className="rounded-hero bg-surface p-6 shadow-card sm:p-8"
            >
              <Icon name="quote" size={28} className="text-brand-text" />
              <blockquote className="mt-3 text-lg font-medium text-ink sm:text-xl">
                {t(`landing.voices.${p}.quote`)}
              </blockquote>
              <figcaption className="mt-4 text-sm">
                <span className="font-bold text-ink">{t(`landing.voices.${p}.name`)}</span>
                <span className="text-muted"> · {t(`landing.voices.${p}.role`)}</span>
              </figcaption>
            </figure>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button type="button" aria-label={t("landing.voices.prev")} className={ctl} onClick={() => setIndex((index + total - 1) % total)}>
            <Icon name="chevron" className="rotate-180 rtl:rotate-0" />
          </button>
          <button type="button" aria-label={t("landing.voices.next")} className={ctl} onClick={() => setIndex((index + 1) % total)}>
            <Icon name="chevron" className="rtl:rotate-180" />
          </button>
          <div className="flex items-center">
            {PERSONAS.map((p, i) => (
              <button
                key={p}
                type="button"
                aria-label={t("landing.voices.goTo", { n: i + 1 })}
                aria-current={i === index ? "true" : undefined}
                onClick={() => setIndex(i)}
                className="flex size-11 items-center justify-center rounded-full focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
              >
                <span
                  className={`block size-3 rounded-full border-2 border-brand-700 ${i === index ? "bg-brand-700" : "bg-surface"}`}
                />
              </button>
            ))}
          </div>
          {!reduced ? (
            <button
              type="button"
              aria-pressed={userPaused}
              onClick={() => setUserPaused((v) => !v)}
              className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-brand-text hover:bg-brand-50 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              <Icon name={userPaused ? "play" : "clock"} size={16} />
              {userPaused ? t("landing.voices.play") : t("landing.voices.pause")}
            </button>
          ) : null}
        </div>
      </div>
    </Section>
  );
}
