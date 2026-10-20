"use client";

import { useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { useT } from "@/i18n";

import { PrivacyXray } from "./PrivacyXray";

type Props = { kind: "message" | "document"; id: string };

export function XrayButton({ kind, id }: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t("privacy.xray.open")}
        title={t("privacy.xray.open")}
        data-testid="xray-button"
        onClick={() => setOpen(true)}
        className="inline-flex size-9 items-center justify-center rounded-lg text-muted hover:bg-surface-alt hover:text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </button>
      {open ? (
        <Modal title={t("privacy.xray.title")} size="xl" onClose={() => setOpen(false)}>
          <PrivacyXray kind={kind} id={id} />
        </Modal>
      ) : null}
    </>
  );
}
