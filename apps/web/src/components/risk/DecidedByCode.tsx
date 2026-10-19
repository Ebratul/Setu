"use client";

import { useId, useState } from "react";

import { useT } from "@/i18n";

export function DecidedByCode() {
  const t = useT();
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
    >
      <button
        type="button"
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="inline-flex items-center gap-1 rounded-full border border-brand-700 bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <span aria-hidden="true">⚙</span>
        {t("risk.code.badge")}
        <span aria-hidden="true" className="text-muted">ⓘ</span>
        <span className="sr-only">{t("risk.code.help")}</span>
      </button>
      {open ? (
        <span
          id={id}
          role="tooltip"
          className="absolute left-0 z-20 mt-2 block w-72 max-w-[80vw] rounded-xl border border-line bg-surface p-3 text-xs font-normal text-ink shadow-card-hover"
        >
          {t("risk.code.body")}
        </span>
      ) : null}
    </span>
  );
}
