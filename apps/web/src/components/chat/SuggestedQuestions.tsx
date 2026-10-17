"use client";

import { useT } from "@/i18n";

const KEYS = ["cash", "landed", "financing", "fx", "alerts", "suppliers"] as const;

export function SuggestedQuestions({ onPick }: { onPick: (q: string) => void }) {
  const t = useT();
  return (
    <section aria-labelledby="chat-suggest-h" className="space-y-3">
      <h2 id="chat-suggest-h" className="text-sm font-semibold text-muted">
        {t("chat.suggest.title")}
      </h2>
      <ul className="flex flex-wrap gap-2">
        {KEYS.map((k) => {
          const q = t(`chat.suggest.${k}`);
          return (
            <li key={k} className="max-w-full">
              <button
                type="button"
                onClick={() => onPick(q)}
                className="max-w-full rounded-full border border-brand-600 bg-surface px-3 py-1.5 text-left text-sm font-semibold break-words text-brand-700 hover:bg-brand-50 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
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
