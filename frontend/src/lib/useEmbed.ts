"use client";

import { useSyncExternalStore } from "react";

const KEY = "setu_embed";

/**
 * Embed mode: the real app inside the guided-demo iframe. `?embed=1` switches it on (`embed=0` off); inside an
 * iframe it then sticks for the rest of the session. Outside an iframe only the URL parameter counts, so the
 * parent tab never inherits it through the shared sessionStorage.
 */
export function readEmbed(): boolean {
  if (typeof window === "undefined") return false;
  const inFrame = window.self !== window.top;
  let param: string | null = null;
  try {
    param = new URLSearchParams(window.location.search).get("embed");
  } catch {
    param = null;
  }
  try {
    if (param === "1") {
      if (inFrame) sessionStorage.setItem(KEY, "1");
      return true;
    }
    if (param === "0") {
      sessionStorage.removeItem(KEY);
      return false;
    }
    return inFrame && sessionStorage.getItem(KEY) === "1";
  } catch {
    return param === "1";
  }
}

const noop = () => () => {};

export function useEmbed(): boolean {
  return useSyncExternalStore(noop, readEmbed, () => false);
}
