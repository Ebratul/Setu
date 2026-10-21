"use client";

import { useEffect, useState } from "react";

import {
  getPublicAuthConfig,
  type AuthMode,
  type PublicAuthConfig,
} from "./client";

export type ModeState = {
  mode: AuthMode | null;
  config: PublicAuthConfig | null;
  failed: boolean;
  retry: () => void;
};

export function useAuthMode(): ModeState {
  const [state, setState] = useState<{
    config: PublicAuthConfig | null;
    failed: boolean;
  }>({
    config: null,
    failed: false,
  });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    getPublicAuthConfig().then(
      (config) => live && setState({ config, failed: false }),
      () => live && setState({ config: null, failed: true }),
    );
    return () => {
      live = false;
    };
  }, [tick]);
  return {
    mode: state.config?.mode ?? null,
    ...state,
    retry: () => setTick((n) => n + 1),
  };
}
