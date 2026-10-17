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
  en: flatten(en as Dict),
  bn: flatten(bn as Dict),
  zh: flatten(zh as Dict),
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
