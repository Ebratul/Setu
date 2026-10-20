"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getAuditEntries, type AuditEntry } from "@/lib/api/audit";
import { useTabVisible } from "@/lib/useHref";
import { usePoll } from "@/lib/usePoll";

const KEEP = 150;

/** Latest entries, then `?after=<last seq>` every 2 s while the tab is visible. */
export function useAuditFeed(pollMs = 2000) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [fresh, setFresh] = useState<ReadonlySet<number>>(new Set());
  const [error, setError] = useState<unknown>(null);
  const [loaded, setLoaded] = useState(false);
  const last = useRef(0);
  const busy = useRef(false);
  const visible = useTabVisible();

  const pull = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const initial = last.current === 0;
      const res = await getAuditEntries({ after: last.current, limit: initial ? 30 : 100 });
      setError(null);
      setLoaded(true);
      if (res.rows.length === 0) return;
      last.current = res.rows[res.rows.length - 1].seq;
      setEntries((prev) => [...prev, ...res.rows].slice(-KEEP));
      if (!initial) setFresh(new Set(res.rows.map((r) => r.seq)));
    } catch (e) {
      setError(e);
    } finally {
      busy.current = false;
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => void pull(), 0);
    return () => clearTimeout(id);
  }, [pull]);
  usePoll(() => void pull(), pollMs, visible);
  return { entries, fresh, error, loaded, reload: pull };
}
