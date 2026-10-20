"use client";

import { createContext } from "react";

export const GENERIC_PROMPTS = ["cash", "landed", "financing", "fx", "alerts", "suppliers", "kb"].map(
  (k) => `chat.suggest.${k}`,
);

/** Three suggested-prompt keys for the page the user is on; null falls back to the generic set. */
export function promptKeysFor(pathname: string | null): string[] | null {
  if (!pathname) return null;
  if (pathname === "/app") {
    return ["chat.suggest.cash", "chat.suggest.alerts", "chat.suggest.suppliers"];
  }
  if (pathname.startsWith("/app/cashflow")) {
    return ["chat.suggest.cash", "chatx.p.cashflow2", "chat.suggest.alerts"];
  }
  if (pathname.startsWith("/app/financing")) {
    return ["chat.suggest.financing", "chat.suggest.fx", "chatx.p.financing2"];
  }
  if (pathname.startsWith("/app/approvals")) {
    return ["chatx.p.approvals1", "chatx.p.approvals2", "chatx.p.approvals3"];
  }
  if (/^\/app\/(?:orders|deals)\/[^/]+\/analysis/.test(pathname) || pathname.startsWith("/app/analysis")) {
    return ["chat.suggest.landed", "chatx.p.analysis2", "chatx.p.analysis3"];
  }
  if (/^\/app\/(?:orders|deals)\/(?!new(?:\/|$))[^/]+/.test(pathname)) {
    return ["chat.suggest.landed", "chatx.p.deal2", "chatx.p.deal3"];
  }
  return null;
}

/** Provided by ChatDrawer so the shared panel can show page-specific prompts; absent on the full chat page. */
export const PromptPathContext = createContext<string | null>(null);
