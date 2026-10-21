"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import { useShellUser } from "@/lib/MeContext";
import { useApi } from "@/lib/useApi";

import {
  markVisited,
  ONBOARD_EVENT,
  readOnboard,
  writeOnboard,
  type OnboardItemId,
  type OnboardState,
} from "./onboarding";

type Item = { id: OnboardItemId; href: string; label: string; hint: string };

/** First-visit checklist. Progress and dismissal are stored per user; works (per page view) without storage. */
export function OnboardingChecklist() {
  const t = useT();
  const shellUser = useShellUser();
  const fetched = useApi((s) => getMe(s), "me", !shellUser);
  const me = { data: shellUser ?? fetched.data };
  const userId = me.data?.id;
  const role = me.data?.role;
  // Read synchronously when the user is already known: inserting the card after first paint shifts the whole dashboard.
  const [state, setState] = useState<OnboardState | null>(() =>
    typeof window !== "undefined" && userId ? readOnboard(userId) : null,
  );

  const load = useCallback(() => {
    if (userId) setState(readOnboard(userId));
  }, [userId]);
  useEffect(() => {
    const id = setTimeout(load, 0);
    window.addEventListener(ONBOARD_EVENT, load);
    return () => {
      clearTimeout(id);
      window.removeEventListener(ONBOARD_EVENT, load);
    };
  }, [load]);

  if (!userId || !state || (role !== "BUYER" && role !== "ADMIN" && role !== "JUDGE")) return null;
  const staff = role === "ADMIN" || role === "JUDGE";

  const items: Item[] = [
    { id: "orders", href: "/app/deals", label: t("onboard.explore"), hint: t("onboard.exploreHint") },
    { id: "cashflow", href: "/app/cashflow", label: t("onboard.cashflow"), hint: t("onboard.cashflowHint") },
    staff
      ? { id: "demo", href: "/demo/attack-console", label: t("onboard.attack"), hint: t("onboard.attackHint") }
      : { id: "demo", href: "/demo/scam-simulator", label: t("onboard.scam"), hint: t("onboard.scamHint") },
  ];
  const done = items.filter((i) => state.visited.includes(i.id)).length;

  function setDismissed(dismissed: boolean) {
    const next = { ...state!, dismissed };
    setState(next);
    writeOnboard(userId!, next);
  }

  if (state.dismissed) {
    return (
      <div>
        <Button variant="ghost" size="sm" data-testid="onboard-show" onClick={() => setDismissed(false)}>
          {t("onboard.show")}
        </Button>
      </div>
    );
  }

  return (
    <div data-testid="onboarding">
    <Card as="section" labelledBy="onboard-h" className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="onboard-h" className="text-lg font-bold text-ink">
            {t("onboard.title")}
          </h2>
          <p className="text-sm text-muted">{done === items.length ? t("onboard.allDone") : t("onboard.sub")}</p>
        </div>
        <Button variant="secondary" size="sm" className="min-h-11" onClick={() => setDismissed(true)}>
          {t("onboard.dismiss")}
        </Button>
      </div>
      <p className="text-sm font-semibold text-ink" aria-live="polite">
        {t("onboard.progress", { done, total: items.length })}
      </p>
      <div aria-hidden="true" className="h-2 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full bg-brand-700 transition-[width] duration-300" style={{ width: `${(done / items.length) * 100}%` }} />
      </div>
      <ul className="grid gap-2 md:grid-cols-3">
        {items.map((i) => {
          const ok = state.visited.includes(i.id);
          return (
            <li key={i.id} data-done={ok}>
              <Link
                href={i.href}
                onClick={() => markVisited(userId, i.id)}
                className="flex min-h-11 items-start gap-3 rounded-xl border border-line p-3 hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                <span className={`mt-0.5 ${ok ? "text-success" : "text-muted"}`}>
                  <Icon name={ok ? "check" : "circle"} />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold break-words text-ink">{i.label}</span>
                  <span className="block text-xs text-muted">{i.hint}</span>
                  <span className="mt-1 block text-xs font-semibold text-ink">{ok ? t("onboard.done") : t("onboard.todo")}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
    </div>
  );
}
