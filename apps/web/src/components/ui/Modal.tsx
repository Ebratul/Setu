"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

import { useT } from "@/i18n";

type Props = {
  title: string;
  onClose: () => void;
  children: ReactNode;
  closeDisabled?: boolean;
};

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Accessible modal: focus trap, Esc closes, focus returns to the opener. */
export function Modal({ title, onClose, children, closeDisabled }: Props) {
  const t = useT();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const disabledRef = useRef(closeDisabled);
  useEffect(() => {
    onCloseRef.current = onClose;
    disabledRef.current = closeDisabled;
  });

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const el = panel.current;
    el?.focus();
    function onKey(e: KeyboardEvent) {
      if (!el) return;
      if (e.key === "Escape") {
        if (!disabledRef.current) onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const items = Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === el)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      } else if (!el.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 p-0 sm:items-center sm:p-4">
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-card bg-surface p-5 shadow-card-hover focus:outline-none sm:max-w-2xl sm:rounded-card"
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
