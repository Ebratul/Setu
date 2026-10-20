"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";

type Vote = "yes" | "no";
type Stored = { vote: Vote; comment: string; at: string };

const key = (id: string) => `setu_docs_feedback:${id}`;

/** Thumbs up/down with an optional comment, stored per page in this browser. */
export function PageFeedback({ pageId }: { pageId: string }) {
  const t = useT();
  const [saved, setSaved] = useState<Stored | null>(null);
  const [vote, setVote] = useState<Vote | null>(null);
  const [comment, setComment] = useState("");
  useEffect(() => {
    const id = setTimeout(() => {
      try {
        const raw = localStorage.getItem(key(pageId));
        if (raw) setSaved(JSON.parse(raw) as Stored);
      } catch {
        /* storage unavailable */
      }
    }, 0);
    return () => clearTimeout(id);
  }, [pageId]);

  function submit() {
    if (!vote) return;
    const next: Stored = { vote, comment: comment.trim().slice(0, 500), at: new Date().toISOString() };
    try {
      localStorage.setItem(key(pageId), JSON.stringify(next));
    } catch {
      /* storage unavailable */
    }
    setSaved(next);
  }

  return (
    <section aria-labelledby="docs-feedback" className="no-print mt-10 rounded-card border border-line bg-surface p-4">
      <h2 id="docs-feedback" className="font-semibold text-ink">
        {t("docs.helpful.q")}
      </h2>
      {saved ? (
        <p role="status" className="mt-2 text-sm text-muted">
          {t("docs.helpful.thanks")}
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          <div role="group" aria-label={t("docs.helpful.legend")} className="flex flex-wrap gap-2">
            {(["yes", "no"] as const).map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={vote === v}
                data-testid={`docs-vote-${v}`}
                onClick={() => setVote(v)}
                className={`min-h-11 rounded-xl border px-4 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
                  vote === v ? "border-brand-700 bg-brand-700 text-white" : "border-line text-ink hover:bg-surface-alt"
                }`}
              >
                <span aria-hidden="true">{v === "yes" ? "👍 " : "👎 "}</span>
                {t(`docs.helpful.${v}`)}
              </button>
            ))}
          </div>
          {vote ? (
            <div className="space-y-2">
              <label className="block text-sm text-ink" htmlFor="docs-feedback-comment">
                {t("docs.helpful.comment")}
              </label>
              <textarea
                id="docs-feedback-comment"
                value={comment}
                maxLength={500}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-line bg-surface p-2 text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
              />
              <Button size="sm" onClick={submit}>
                {t("docs.helpful.send")}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
