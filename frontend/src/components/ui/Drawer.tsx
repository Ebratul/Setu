"use client";

import { useId, useRef, type ReactNode } from "react";

import { useT } from "@/i18n";
import { useDialog } from "@/lib/useDialog";

import { Icon } from "./Icon";

type Props = {
  title: string;
  onClose: () => void;
  children: ReactNode;
  side?: "right" | "left";
};

/** Side sheet with the same a11y contract as Modal (focus trap, Esc, focus return). */
export function Drawer({ title, onClose, children, side = "right" }: Props) {
  const t = useT();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  useDialog(panel, onClose);
  return (
    <div className="fixed inset-0 z-50 bg-scrim" onClick={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={`anim-drawer absolute inset-y-0 flex w-full max-w-md flex-col bg-surface shadow-pop focus:outline-none ${
          side === "right" ? "right-0" : "left-0"
        }`}
      >
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 id={titleId} className="text-lg font-bold text-ink">
            {title}
          </h2>
          <button
            type="button"
            aria-label={t("common.close")}
            onClick={onClose}
            className="flex size-11 items-center justify-center rounded-lg text-muted hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
          >
            <Icon name="x" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}
