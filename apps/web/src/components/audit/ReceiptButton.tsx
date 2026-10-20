"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useT } from "@/i18n";

import { ReceiptBody } from "./ReceiptBody";

type Props = { seq: number; className?: string };

/** Opens a signed, scannable receipt for one audit entry. */
export function ReceiptButton({ seq, className = "" }: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="secondary"
        className={`!px-3 !py-1 text-xs ${className}`}
        data-testid="receipt-button"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <span aria-hidden="true">🧾 </span>
        {t("audit.receipt.button")}
        <span className="sr-only"> #{seq}</span>
      </Button>
      {open ? (
        <Modal title={t("audit.receipt.title")} onClose={() => setOpen(false)}>
          <ReceiptBody seq={seq} />
        </Modal>
      ) : null}
    </>
  );
}
