"use client";

import { useEffect, useState } from "react";

import { useT } from "@/i18n";
import { applyTheme, readThemeChoice, type ThemeChoice } from "@/lib/theme";

import { Icon } from "./Icon";

const NEXT: Record<ThemeChoice, ThemeChoice> = { system: "light", light: "dark", dark: "system" };

/** Cycles system -> light -> dark. Label names the current mode so it is announced, not guessed. */
export function ThemeToggle() {
  const t = useT();
  const [choice, setChoice] = useState<ThemeChoice>("system");
  useEffect(() => {
    const id = setTimeout(() => setChoice(readThemeChoice()), 0);
    return () => clearTimeout(id);
  }, []);
  return (
    <button
      type="button"
      data-testid="theme-toggle"
      aria-label={t("ui.theme.label", { mode: t(`ui.theme.${choice}`) })}
      title={t(`ui.theme.${choice}`)}
      onClick={() => {
        const next = NEXT[choice];
        setChoice(next);
        applyTheme(next);
      }}
      className="flex size-11 items-center justify-center rounded-xl border border-line text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      <Icon name={choice === "dark" ? "moon" : choice === "light" ? "sun" : "globe"} />
    </button>
  );
}
