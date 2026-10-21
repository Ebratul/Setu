"use client";

import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/ui/ThemeToggle";

import { LanguageToggle } from "./LanguageToggle";

type Props = { code: string; title: string; body: string; note?: string; children: ReactNode };

export const statusLink =
  "inline-flex min-h-11 items-center justify-center rounded-xl px-4 py-2 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

/** Full-page frame for 404 / 500: language and theme stay switchable, one h1, actions below. */
export function StatusPage({ code, title, body, note, children }: Props) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex flex-wrap items-center justify-end gap-3 px-4 py-3">
        <LanguageToggle withZh />
        <ThemeToggle />
      </header>
      <main id="main" className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center gap-4 px-4 py-10 text-center">
        <p aria-hidden="true" className="text-6xl font-extrabold text-brand-text">
          {code}
        </p>
        <h1 className="text-2xl font-bold text-ink">{title}</h1>
        <p className="text-muted">{body}</p>
        {note ? <p className="text-xs break-all text-muted">{note}</p> : null}
        <div className="flex flex-wrap items-center justify-center gap-3">{children}</div>
      </main>
    </div>
  );
}
