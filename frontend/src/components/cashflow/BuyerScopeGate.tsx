"use client";

import type { ReactNode } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { FormField, inputClass } from "@/components/ui/FormField";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";

import { useBuyerScope } from "./useBuyerScope";

type Props = { children: (partyId: string | undefined) => ReactNode };

export function BuyerScopeGate({ children }: Props) {
  const t = useT();
  const scope = useBuyerScope();

  if (scope.error) {
    return <QueryError error={scope.error} onRetry={scope.reload} />;
  }
  return (
    <div className="space-y-6">
      {scope.needsPicker ? (
        <div className="w-64">
          <FormField id="scope-buyer" label={t("monthly.pickBuyer")}>
            {(aria) => (
              <select
                {...aria}
                value={scope.party}
                onChange={(e) => scope.setParty(e.target.value)}
                className={inputClass}
              >
                <option value="">{t("monthly.chooseBuyer")}</option>
                {scope.buyers.map((b) => (
                  <option key={b.party_id} value={b.party_id ?? ""}>
                    {b.party_name}
                  </option>
                ))}
              </select>
            )}
          </FormField>
        </div>
      ) : null}
      {!scope.ready ? (
        scope.needsPicker ? (
          <EmptyState title={t("cf.chooseBuyerFirst")} />
        ) : (
          <div aria-busy="true" className="space-y-4">
            <Skeleton className="h-28" />
            <Skeleton className="h-64" />
          </div>
        )
      ) : (
        <div key={scope.party}>{children(scope.party || undefined)}</div>
      )}
    </div>
  );
}
