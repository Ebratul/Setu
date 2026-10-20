"use client";

import { useEffect, useState } from "react";

import { getAuthMode, type AuthMode } from "./client";

export type ModeState = { mode: AuthMode | null; failed: boolean; retry: () => void };

export function useAuthMode(): ModeState {
  const [state, setState] = useState<{ mode: AuthMode | null; failed: boolean }>({
    mode: null,
    failed: false,
  });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    getAuthMode().then(
      (mode) => live && setState({ mode, failed: false }),
      () => live && setState({ mode: null, failed: true }),
    );
    return () => {
      live = false;
    };
  }, [tick]);
  return { ...state, retry: () => setTick((n) => n + 1) };
}
