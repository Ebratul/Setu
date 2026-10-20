"use client";

import { useCallback, useSyncExternalStore } from "react";

import { loadReadAloud, saveReadAloud } from "./speech";

const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
};
const noopSubscribe = () => () => {};

/** Persisted read-aloud preference (localStorage, guarded) and whether the browser can speak at all. */
export function useReadAloud(): { on: boolean; setOn: (v: boolean) => void; supported: boolean } {
  const on = useSyncExternalStore(subscribe, loadReadAloud, () => false);
  const supported = useSyncExternalStore(
    noopSubscribe,
    () => typeof window !== "undefined" && "speechSynthesis" in window,
    () => false,
  );
  const setOn = useCallback((v: boolean) => {
    saveReadAloud(v);
    listeners.forEach((l) => l());
  }, []);
  return { on, setOn, supported };
}
