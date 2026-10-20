"use client";

import { useEffect, useState } from "react";

import { getHealth, type HealthResponse } from "@/lib/api/client";

import { StatusRow } from "./StatusRow";

const POLL_MS = 10_000;
const TIMEOUT_MS = 5_000;

type Status =
  | { kind: "loading" }
  | { kind: "online"; health: HealthResponse }
  | { kind: "offline" };

export function AgentStatusCard() {
  const [status, setStatus] = useState<Status>({ kind: "loading" });

  useEffect(() => {
    let active = true;

    async function check() {
      try {
        const health = await getHealth(AbortSignal.timeout(TIMEOUT_MS));
        if (active) setStatus({ kind: "online", health });
      } catch {
        if (active) setStatus({ kind: "offline" });
      }
    }

    void check();
    const id = setInterval(check, POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const agentOnline = status.kind === "online";
  const dbOk = status.kind === "online" && status.health.db === "ok";

  return (
    <section
      aria-labelledby="status-heading"
      className="w-full max-w-sm rounded-card bg-surface p-6 shadow-card"
    >
      <h2 id="status-heading" className="text-lg font-semibold">
        System status
      </h2>
      <dl aria-live="polite" className="mt-2 divide-y divide-surface-alt">
        <StatusRow
          label="Agent"
          value={
            status.kind === "loading"
              ? "checking"
              : agentOnline
                ? "online"
                : "offline"
          }
          good={status.kind === "loading" ? null : agentOnline}
        />
        <StatusRow
          label="DB"
          value={
            status.kind === "loading" ? "checking" : dbOk ? "ok" : "unavailable"
          }
          good={status.kind === "loading" ? null : dbOk}
        />
      </dl>
      {status.kind === "online" && (
        <p className="mt-3 text-sm text-muted">
          Agent version {status.health.version}
        </p>
      )}
    </section>
  );
}
