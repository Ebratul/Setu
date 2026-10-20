"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import bn from "./bn.json";
import en from "./en.json";
import zh from "./zh.json";
import demoBn from "./parts/demo.bn.json";
import demoEn from "./parts/demo.en.json";
import demoZh from "./parts/demo.zh.json";
import landingBn from "./parts/landing.bn.json";
import landingEn from "./parts/landing.en.json";
import landingZh from "./parts/landing.zh.json";
import onboardBn from "./parts/onboard.bn.json";
import paypalBn from "./parts/paypal.bn.json";
import onboardEn from "./parts/onboard.en.json";
import paypalEn from "./parts/paypal.en.json";
import onboardZh from "./parts/onboard.zh.json";
import paypalZh from "./parts/paypal.zh.json";
import pagesBn from "./parts/pages.bn.json";
import pagesEn from "./parts/pages.en.json";
import pagesZh from "./parts/pages.zh.json";
import shellBn from "./parts/shell.bn.json";
import shellEn from "./parts/shell.en.json";
import shellZh from "./parts/shell.zh.json";
import uiBn from "./parts/ui.bn.json";
import uiEn from "./parts/ui.en.json";
import uiZh from "./parts/ui.zh.json";

export type Lang = "en" | "bn" | "zh";
type Dict = { [key: string]: string | Dict };
type Vars = Record<string, string | number>;

export const LANG_COOKIE = "setu_lang";

function flatten(dict: Dict, prefix = "", out: Record<string, string> = {}) {
  for (const [k, v] of Object.entries(dict)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else flatten(v, key, out);
  }
  return out;
}

export const messages: Record<Lang, Record<string, string>> = {
  en: Object.assign(flatten(en as Dict), flatten(demoEn as Dict), flatten(landingEn as Dict), flatten(pagesEn as Dict), flatten(shellEn as Dict), flatten(uiEn as Dict), flatten(onboardEn as Dict), flatten(paypalEn as Dict)),
  bn: Object.assign(flatten(bn as Dict), flatten(demoBn as Dict), flatten(landingBn as Dict), flatten(pagesBn as Dict), flatten(shellBn as Dict), flatten(uiBn as Dict), flatten(onboardBn as Dict), flatten(paypalBn as Dict)),
  zh: Object.assign(flatten(zh as Dict), flatten(demoZh as Dict), flatten(landingZh as Dict), flatten(pagesZh as Dict), flatten(shellZh as Dict), flatten(uiZh as Dict), flatten(onboardZh as Dict), flatten(paypalZh as Dict)),
};

export function translate(lang: Lang, key: string, vars?: Vars): string {
  const raw = messages[lang][key] ?? messages.en[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (m, name: string) =>
    name in vars ? String(vars[name]) : m,
  );
}

export function hasKey(key: string): boolean {
  return key in messages.en;
}

const listeners = new Set<() => void>();

function readLang(): Lang {
  const m = document.cookie.match(new RegExp(`(?:^|; )${LANG_COOKIE}=(\\w+)`));
  if (m?.[1] === "bn" || m?.[1] === "en" || m?.[1] === "zh") return m[1];
  try {
    const stored = localStorage.getItem(LANG_COOKIE);
    if (stored === "bn" || stored === "en" || stored === "zh") return stored;
  } catch {
    /* storage unavailable */
  }
  return "en";
}

function writeLang(lang: Lang) {
  document.cookie = `${LANG_COOKIE}=${lang}; path=/; max-age=31536000; samesite=lax`;
  try {
    localStorage.setItem(LANG_COOKIE, lang);
  } catch {
    /* storage unavailable */
  }
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

type Ctx = { lang: Lang; setLang: (lang: Lang) => void };

const I18nContext = createContext<Ctx>({ lang: "en", setLang: () => {} });

export function I18nProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore<Lang>(subscribe, readLang, () => "en");
  const setLang = useCallback((next: Lang) => writeLang(next), []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useLang(): Ctx {
  return useContext(I18nContext);
}

export function useT() {
  const { lang } = useContext(I18nContext);
  return useCallback(
    (key: string, vars?: Vars) => translate(lang, key, vars),
    [lang],
  );
}

/** Pick the current-language text from an API `{en, bn}` object. */
export function pickLang(item: { en: string; bn: string }, lang: Lang) {
  return lang === "bn" ? item.bn : item.en;
}
