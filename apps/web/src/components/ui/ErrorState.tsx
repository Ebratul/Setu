"use client";

import { useT } from "@/i18n";

import { Button } from "./Button";

type Props = { onRetry?: () => void; message?: string };

export function ErrorState({ onRetry, message }: Props) {
  const t = useT();
  return (
    <div
      role="alert"
      className="rounded-card border border-danger bg-danger-soft p-6"
    >
      <p className="font-semibold text-danger">{t("error.title")}</p>
      <p className="mt-1 text-sm text-ink">{message ?? t("error.body")}</p>
      {onRetry ? (
        <Button variant="secondary" className="mt-4" onClick={onRetry}>
          {t("common.retry")}
        </Button>
      ) : null}
    </div>
  );
}
