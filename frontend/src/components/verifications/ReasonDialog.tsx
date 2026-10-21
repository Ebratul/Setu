"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";

export const MIN_REASON = 10;
export const MAX_REASON = 500;

type Props = {
  title: string;
  body: string;
  confirmLabel: string;
  busy: boolean;
  error: string | null;
  onConfirm: (reason: string) => void;
  onClose: () => void;
  maxLength?: number;
};

/** Reject, suspend and reveal all need a written reason of at least 10 characters. */
export function ReasonDialog({ title, body, confirmLabel, busy, error, onConfirm, onClose, maxLength = MAX_REASON }: Props) {
  const t = useT();
  const [reason, setReason] = useState("");
  return (
    <ConfirmDialog
      title={title}
      confirmLabel={confirmLabel}
      busy={busy}
      error={error}
      confirmDisabled={reason.trim().length < MIN_REASON}
      onConfirm={() => onConfirm(reason.trim())}
      onClose={onClose}
    >
      <p>{body}</p>
      <FormField id="vq-reason" label={`${t("vq.reason")} *`} hint={t("vq.reasonHint", { min: MIN_REASON })}>
        {(aria) => (
          <textarea {...aria} aria-required rows={4} maxLength={maxLength} value={reason} onChange={(e) => setReason(e.target.value)} className={inputClass} />
        )}
      </FormField>
    </ConfirmDialog>
  );
}
