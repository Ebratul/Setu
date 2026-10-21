"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Result<T> = { key: string; data?: T; error?: unknown };

/** Fetch with abort-on-change. `key` must change whenever the request inputs change. */
export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  key: string,
  enabled = true,
) {
  const [res, setRes] = useState<Result<T>>();
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fetcher);
  useEffect(() => {
    fnRef.current = fetcher;
  });
  const reqKey = `${key}#${tick}`;

  useEffect(() => {
    if (!enabled) return;
    const ac = new AbortController();
    fnRef.current(ac.signal).then(
      (data) => {
        if (!ac.signal.aborted) setRes({ key: reqKey, data });
      },
      (error: unknown) => {
        if (!ac.signal.aborted) setRes({ key: reqKey, error });
      },
    );
    return () => ac.abort();
  }, [reqKey, enabled]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  const settled = res?.key === reqKey;
  return {
    data: res?.error ? undefined : res?.data,
    error: settled ? res?.error : undefined,
    loading: enabled && !settled,
    reload,
  };
}

/** Debounce a value (used for the live calculator / target-price helper). */
export function useDebounced<T>(value: T, ms = 400): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}
