import type { AlertAction, AlertPreview, Severity } from "@/lib/api/cashflow";

const RANK: Record<Severity, number> = { CRITICAL: 0, WARNING: 1, INFO: 2 };

/** Display ordering only: severity first, then earliest due date (undated last). */
export function sortAlerts<T extends Pick<AlertPreview, "severity" | "due_on">>(
  alerts: readonly T[],
): T[] {
  return [...alerts].sort((a, b) => {
    const bySeverity = RANK[a.severity] - RANK[b.severity];
    if (bySeverity !== 0) return bySeverity;
    if (a.due_on === b.due_on) return 0;
    if (!a.due_on) return 1;
    if (!b.due_on) return -1;
    return a.due_on < b.due_on ? -1 : 1;
  });
}

export function actionHref(action: AlertAction): string {
  const qs = new URLSearchParams(action.query).toString();
  return qs ? `${action.route}?${qs}` : action.route;
}
