"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { FormField, inputClass } from "@/components/ui/FormField";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import {
  acknowledgeAlert,
  getAlerts,
  resolveAlert,
  type AlertStatus,
  type AlertType,
  type Severity,
} from "@/lib/api/cashflow";
import { ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/useApi";

import type { AlertView } from "./AlertItem";
import { AlertPanel } from "./AlertPanel";

const TYPES: AlertType[] = [
  "SHORTFALL",
  "DEADLINE",
  "FX_OPPORTUNITY",
  "KYB_WARNING",
  "FRAUD",
  "INFO",
];
const SEVERITIES: Severity[] = ["CRITICAL", "WARNING", "INFO"];
const STATUSES: AlertStatus[] = ["OPEN", "ACKNOWLEDGED", "RESOLVED"];

type Props = { partyId?: string };

export function CashflowAlerts({ partyId }: Props) {
  const t = useT();
  const [type, setType] = useState<"" | AlertType>("");
  const [severity, setSeverity] = useState<"" | Severity>("");
  const [status, setStatus] = useState<"" | AlertStatus>("");
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<"readonly" | "failed" | null>(null);

  const { data, error, loading, reload } = useApi(
    (s) => getAlerts(partyId, status || undefined, s),
    `alerts|${partyId ?? ""}|${status}`,
  );

  const shown: AlertView[] = (data?.alerts ?? []).filter(
    (a) => (!type || a.type === type) && (!severity || a.severity === severity),
  );

  async function act(id: string, fn: (id: string) => Promise<unknown>) {
    setBusy(id);
    setProblem(null);
    try {
      await fn(id);
      reload();
    } catch (e) {
      setProblem(
        e instanceof ApiError && e.status === 403 ? "readonly" : "failed",
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card as="section" labelledBy="alerts-h" className="space-y-4">
      <h3 id="alerts-h" className="text-lg font-semibold text-ink">
        {t("alerts.title")}
      </h3>
      <div className="grid gap-3 sm:grid-cols-3">
        <FormField id="af-type" label={t("alerts.filter.type")}>
          {(aria) => (
            <select
              {...aria}
              value={type}
              onChange={(e) => setType(e.target.value as "" | AlertType)}
              className={inputClass}
            >
              <option value="">{t("alerts.filter.all")}</option>
              {TYPES.map((v) => (
                <option key={v} value={v}>
                  {t(`alertType.${v}`)}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <FormField id="af-severity" label={t("alerts.filter.severity")}>
          {(aria) => (
            <select
              {...aria}
              value={severity}
              onChange={(e) => setSeverity(e.target.value as "" | Severity)}
              className={inputClass}
            >
              <option value="">{t("alerts.filter.all")}</option>
              {SEVERITIES.map((v) => (
                <option key={v} value={v}>
                  {t(`severity.${v}`)}
                </option>
              ))}
            </select>
          )}
        </FormField>
        <FormField id="af-status" label={t("alerts.filter.status")}>
          {(aria) => (
            <select
              {...aria}
              value={status}
              onChange={(e) => setStatus(e.target.value as "" | AlertStatus)}
              className={inputClass}
            >
              <option value="">{t("alerts.filter.all")}</option>
              {STATUSES.map((v) => (
                <option key={v} value={v}>
                  {t(`alertStatus.${v}`)}
                </option>
              ))}
            </select>
          )}
        </FormField>
      </div>
      {problem ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {problem === "readonly"
            ? t("alerts.readOnly")
            : t("alerts.actionFailed")}
        </p>
      ) : null}
      {error ? (
        <QueryError error={error} onRetry={reload} />
      ) : !data ? (
        <div aria-busy="true" className="space-y-2">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : (
        <div aria-busy={loading ? true : undefined}>
          <AlertPanel
            alerts={shown}
            emptyTitle={t("alerts.empty")}
            renderActions={(a) =>
              a.id ? (
                <>
                  {a.status === "OPEN" ? (
                    <Button
                      variant="secondary"
                      disabled={busy !== null}
                      onClick={() => act(a.id as string, acknowledgeAlert)}
                    >
                      {t("alerts.acknowledge")}
                    </Button>
                  ) : null}
                  {a.status !== "RESOLVED" ? (
                    <Button
                      variant="ghost"
                      disabled={busy !== null}
                      onClick={() => act(a.id as string, resolveAlert)}
                    >
                      {t("alerts.resolve")}
                    </Button>
                  ) : null}
                </>
              ) : null
            }
          />
        </div>
      )}
    </Card>
  );
}
