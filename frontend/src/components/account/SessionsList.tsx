"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { recordSessionRevoked } from "@/lib/api/auth";
import { getAuthClient } from "@/lib/auth/client";
import { attempt } from "@/lib/auth/flow";

export type SessionRow = {
  id?: string;
  token: string;
  userAgent?: string | null;
  ipAddress?: string | null;
  createdAt?: string | Date | null;
  expiresAt?: string | Date | null;
};

type Props = { onSignedOutEverywhere: () => void };

function day(v: string | Date | null | undefined) {
  if (!v) return "";
  const d = typeof v === "string" ? new Date(v) : v;
  return Number.isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 16).replace("T", " ");
}

export function SessionsList({ onSignedOutEverywhere }: Props) {
  const t = useT();
  const [rows, setRows] = useState<SessionRow[] | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const auth = getAuthClient();
    const [list, me] = await Promise.all([
      attempt<SessionRow[]>(() => auth.listSessions() as Promise<{ data?: SessionRow[] | null; error?: unknown }>),
      attempt<{ session?: { token?: string } }>(() => auth.getSession() as Promise<{ data?: { session?: { token?: string } } | null; error?: unknown }>),
    ]);
    if (list.error) {
      setError(t("as.sessions.failed"));
      return;
    }
    setRows(list.data ?? []);
    setCurrent(me.data?.session?.token ?? null);
  }, [t]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function revoke(token: string) {
    setBusy(token);
    setError(null);
    const res = await attempt(() => getAuthClient().revokeSession({ token }) as Promise<{ data?: unknown; error?: unknown }>);
    setBusy(null);
    if (res.error) setError(t("as.sessions.failed"));
    else {
      void recordSessionRevoked("one");
      await load();
    }
  }

  async function revokeOthers() {
    setBusy("others");
    setError(null);
    const res = await attempt(() => getAuthClient().revokeOtherSessions() as Promise<{ data?: unknown; error?: unknown }>);
    setBusy(null);
    if (res.error) setError(t("as.sessions.failed"));
    else {
      void recordSessionRevoked("others");
      await load();
    }
  }

  async function revokeAll() {
    setBusy("all");
    setError(null);
    const res = await attempt(() => getAuthClient().revokeSessions() as Promise<{ data?: unknown; error?: unknown }>);
    setBusy(null);
    if (res.error) setError(t("as.sessions.failed"));
    else {
      await recordSessionRevoked("all");
      onSignedOutEverywhere();
    }
  }

  return (
    <div className="space-y-3">
      {error ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {error}
        </p>
      ) : null}
      {rows === null && !error ? <p role="status">{t("common.loading")}</p> : null}
      {rows ? (
        <ul className="divide-y divide-line rounded-card border border-line bg-surface">
          {rows.map((s) => (
            <li key={s.token} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
              <div className="min-w-0">
                <p className="font-semibold break-words text-ink">{s.userAgent || t("as.sessions.unknownDevice")}</p>
                <p className="text-muted">
                  {[s.ipAddress, day(s.createdAt)].filter(Boolean).join(" · ")}
                </p>
              </div>
              {s.token === current ? (
                <Badge tone="info">{t("as.sessions.current")}</Badge>
              ) : (
                <Button size="sm" variant="secondary" loading={busy === s.token} onClick={() => void revoke(s.token)} aria-label={`${t("as.sessions.signOut")}: ${s.userAgent ?? ""}`}>
                  {t("as.sessions.signOut")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" loading={busy === "others"} onClick={() => void revokeOthers()}>
          {t("as.sessions.others")}
        </Button>
        <Button variant="danger" loading={busy === "all"} onClick={() => void revokeAll()}>
          {t("as.sessions.all")}
        </Button>
      </div>
    </div>
  );
}
