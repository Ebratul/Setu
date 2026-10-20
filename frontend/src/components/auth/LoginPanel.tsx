"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { QueryError } from "@/components/ui/QueryError";
import { useT } from "@/i18n";
import { demoLogin, getDemoUsers } from "@/lib/api/auth";
import { safeNext } from "@/lib/auth/flow";
import { useApi } from "@/lib/useApi";

export function LoginPanel() {
  const t = useT();
  const router = useRouter();
  const params = useSearchParams();
  const { data, error, loading, reload } = useApi(getDemoUsers, "demo-users");
  const [pending, setPending] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  async function login(email: string) {
    setPending(email);
    setFailed(false);
    try {
      const user = await demoLogin(email);
      router.replace(safeNext(params.get("next"), user.role));
    } catch {
      setFailed(true);
      setPending(null);
    }
  }

  if (error) return <QueryError error={error} onRetry={reload} />;
  if (loading || !data) {
    return (
      <div aria-busy="true" className="space-y-3">
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {failed ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {t("login.failed")}
        </p>
      ) : null}
      <ul className="space-y-3">
        {data.users.map((u) => (
          <li key={u.id}>
            <Card className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-semibold text-ink">{u.display_name}</p>
                <p className="text-sm text-muted">
                  {t(`role.${u.role}`)} · {u.party_name}
                </p>
              </div>
              <Button
                onClick={() => login(u.email)}
                disabled={pending !== null}
                aria-label={t("login.loginAs", { name: u.display_name })}
              >
                {pending === u.email ? t("common.loading") : t("login.button")}
              </Button>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
