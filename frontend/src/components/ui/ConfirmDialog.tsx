"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useT } from "@/i18n";

type Props = {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  error?: string | null;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onClose: () => void;
};

/** Confirmation built on the focus-trapped Modal; errors render in an alert inside the dialog. */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  busy = false,
  error,
  confirmDisabled = false,
  onConfirm,
  onClose,
}: Props) {
  const t = useT();
  return (
    <Modal title={title} onClose={onClose} closeDisabled={busy}>
      <div className="space-y-4 text-sm text-ink">
        {children}
        {error ? (
          <p
            role="alert"
            className="rounded-xl border border-danger bg-danger-soft p-3 font-medium text-danger"
          >
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button onClick={onConfirm} disabled={busy || confirmDisabled}>
            {busy ? t("common.loading") : confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
