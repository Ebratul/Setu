"use client";

import { useContext } from "react";

import { useT } from "@/i18n";

import { GENERIC_PROMPTS, promptKeysFor, PromptPathContext } from "./pagePrompts";

export function SuggestedQuestions({ onPick }: { onPick: (q: string) => void }) {
  const t = useT();
  const keys = promptKeysFor(useContext(PromptPathContext)) ?? GENERIC_PROMPTS;
  return (
    <section aria-labelledby="chat-suggest-h" className="space-y-3">
      <h2 id="chat-suggest-h" className="text-sm font-semibold text-muted">
        {t("chat.suggest.title")}
      </h2>
      <ul className="flex flex-wrap gap-2">
        {keys.map((k) => {
          const q = t(k);
          return (
            <li key={k} className="max-w-full">
              <button
                type="button"
                onClick={() => onPick(q)}
                className="min-h-11 max-w-full rounded-full border border-brand-600 bg-surface px-3 py-1.5 text-left text-sm font-semibold break-words text-brand-text hover:bg-brand-50 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                {q}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
