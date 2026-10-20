"use client";

import { useId, useRef, type ReactNode } from "react";

import { useT } from "@/i18n";
import { useDialog } from "@/lib/useDialog";

type Props = {
  title: string;
  onClose: () => void;
  children: ReactNode;
  closeDisabled?: boolean;
  size?: "md" | "xl";
};

/** Accessible modal: focus trap, Esc closes, focus returns to the opener. */
export function Modal({ title, onClose, children, closeDisabled, size = "md" }: Props) {
  const t = useT();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  useDialog(panel, onClose, closeDisabled);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-scrim p-0 sm:items-center sm:p-4">
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`max-h-[92vh] w-full overflow-y-auto rounded-t-card bg-surface p-5 shadow-pop focus:outline-none anim-pop ${size === "xl" ? "sm:max-w-5xl" : "sm:max-w-2xl"} sm:rounded-card`}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 id={titleId} className="text-lg font-bold text-ink">
            {title}
          </h2>
          <button
            type="button"
            aria-label={t("common.close")}
            disabled={closeDisabled}
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-lg leading-none text-muted hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none disabled:opacity-50"
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
