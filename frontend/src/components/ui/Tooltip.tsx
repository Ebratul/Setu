"use client";

import { useId, useState, type ReactNode } from "react";

import { Icon } from "./Icon";

type Props = { label: string; children?: ReactNode };

/** Hover/focus tooltip. Default trigger is an info button; Esc dismisses (WCAG 1.4.13). */
export function Tooltip({ label, children }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
    >
      <button
        type="button"
        aria-describedby={open ? id : undefined}
        aria-label={label}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-full text-muted hover:text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
      >
        {children ?? <Icon name="info" size={16} />}
      </button>
      {open ? (
        <span
          role="tooltip"
          id={id}
          className="anim-pop absolute bottom-full left-1/2 z-40 mb-2 w-64 -translate-x-1/2 rounded-lg bg-ink px-3 py-2 text-xs font-medium text-surface shadow-pop"
        >
          {label}
        </span>
      ) : null}
    </span>
  );
}
