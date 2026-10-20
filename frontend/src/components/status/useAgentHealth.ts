"use client";

import { useEffect, useState } from "react";

import { ApiError, getHealth } from "@/lib/api/client";
import { parseHealth, type AgentHealth } from "@/lib/health";

export const HEALTH_POLL_MS = 60_000;
const TIMEOUT_MS = 8_000;

export type HealthState =
  | { kind: "loading" }
  | { kind: "ready"; health: AgentHealth }
  | { kind: "unreachable" };

/** Polls /api/health every 60 s; paused while the tab is hidden, refreshed when it becomes visible. */
export function useAgentHealth(
  intervalMs: number = HEALTH_POLL_MS,
): HealthState {
  const [state, setState] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    let ctrl: AbortController | null = null;
    let disposed = false;

    async function check() {
      ctrl?.abort();
      const c = new AbortController();
      ctrl = c;
      const timer = setTimeout(() => c.abort(), TIMEOUT_MS);
      try {
        const raw: unknown = await getHealth(c.signal);
        if (!disposed && !c.signal.aborted)
          setState({ kind: "ready", health: parseHealth(raw) });
      } catch (e) {
        if (disposed || ctrl !== c) return;
        // 503 from the agent means "up but not ready"; anything else (proxy errors, network) is unreachable.
        if (e instanceof ApiError && e.status === 503)
          setState({
            kind: "ready",
            health: { ...parseHealth({}), status: "degraded" },
          });
        else setState({ kind: "unreachable" });
      } finally {
        clearTimeout(timer);
      }
    }

    const tick = () => {
      if (document.visibilityState !== "hidden") void check();
    };
    tick();
    const id = setInterval(tick, intervalMs);
    document.addEventListener("visibilitychange", tick);
    return () => {
      disposed = true;
      clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
      ctrl?.abort();
    };
  }, [intervalMs]);

  return state;
}
