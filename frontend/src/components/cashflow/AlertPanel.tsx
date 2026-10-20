"use client";

import type { ReactNode } from "react";

import { EmptyState } from "@/components/ui/EmptyState";

import { AlertItem, type AlertView } from "./AlertItem";
import { sortAlerts } from "./alertUtils";

type Props = {
  alerts: readonly AlertView[];
  emptyTitle: string;
  renderActions?: (alert: AlertView) => ReactNode;
};

/** Shows alerts critical-first, then by due date (client-side display ordering only). */
export function AlertPanel({ alerts, emptyTitle, renderActions }: Props) {
  if (alerts.length === 0) return <EmptyState title={emptyTitle} />;
  return (
    <ul aria-live="polite" className="space-y-3">
      {sortAlerts(alerts).map((a) => (
        <AlertItem key={a.id ?? a.key} alert={a} actions={renderActions?.(a)} />
      ))}
    </ul>
  );
}
