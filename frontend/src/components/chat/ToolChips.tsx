"use client";

import { hasKey, useT } from "@/i18n";

import type { ToolStep } from "./types";

const ICON = { running: "…", ok: "✓", error: "✕" } as const;

export function ToolChips({ tools }: { tools: ToolStep[] }) {
  const t = useT();
  if (tools.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label={t("chat.tool.label")}>
      {tools.map((s) => {
        const key = `chat.tool.${s.name}`;
        const label = hasKey(key) ? t(key) : t("chat.tool.generic");
        const tone =
          s.status === "error"
            ? "border-danger bg-danger-soft text-danger"
            : s.status === "ok"
              ? "border-success bg-success-soft text-success"
              : "border-line bg-surface-alt text-ink";
        return (
          <li
            key={s.id}
            data-tool={s.name}
            data-status={s.status}
            className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${tone}`}
          >
            <span aria-hidden="true">{ICON[s.status]}</span>
            <span className="min-w-0 break-words">{label}</span>
            {s.status === "error" ? (
              <span className="sr-only">{t("chat.tool.failed")}</span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
