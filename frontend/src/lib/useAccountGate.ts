"use client";

import { useT } from "@/i18n";
import { useShellUser } from "@/lib/MeContext";

export type MoneyGate = { allowed: boolean; reason: string | null };

/** Money actions need an ACTIVE account. Unknown status (older server, no shell) counts as allowed. */
export function useMoneyGate(): MoneyGate {
  const t = useT();
  const me = useShellUser();
  const status = me?.account_status;
  if (!status || status === "ACTIVE") return { allowed: true, reason: null };
  return { allowed: false, reason: t("vb.locked.reason") };
}
