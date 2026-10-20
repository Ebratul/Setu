"use client";

import { useEffect, useState } from "react";

import { useLang } from "@/i18n";
import { formatDecimal } from "@/lib/format";

type Props = { value: string; format?: (v: string) => string; durationMs?: number };

function scaled(v: string): { n: bigint; scale: number } | null {
  const m = /^(-?)(\d{1,15})(?:\.(\d{1,6}))?$/.exec(v);
  if (!m) return null;
  const frac = m[3] ?? "";
  const n = BigInt(`${m[2]}${frac}`) * BigInt(m[1] ? -1 : 1);
  return { n, scale: frac.length };
}

function unscale(n: bigint, scale: number): string {
  const neg = n < BigInt(0);
  const s = (neg ? -n : n).toString().padStart(scale + 1, "0");
  const whole = s.slice(0, s.length - scale);
  const frac = scale ? s.slice(s.length - scale) : "";
  return `${neg ? "-" : ""}${whole}${frac ? `.${frac}` : ""}`;
}

/**
 * Animates a decimal string with BigInt-scaled integers (no floats), then shows the exact server value.
 * Skipped for reduced motion and in tests.
 */
export function CountUp({ value, format, durationMs = 700 }: Props) {
  const { lang } = useLang();
  const fmt = format ?? ((v: string) => formatDecimal(v, lang, 2));
  const [shown, setShown] = useState(value);

  useEffect(() => {
    const target = scaled(value);
    const reduce = (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
    if (!target || reduce || durationMs <= 0 || typeof requestAnimationFrame === "undefined") {
      const id = setTimeout(() => setShown(value), 0);
      return () => clearTimeout(id);
    }
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - p) * (1 - p) * (1 - p);
      const step = (target.n * BigInt(Math.round(eased * 1000))) / BigInt(1000);
      setShown(p >= 1 ? value : unscale(step, target.scale));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, durationMs]);

  return <span className="tabular-nums">{fmt(shown)}</span>;
}
