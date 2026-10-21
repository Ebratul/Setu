import { sanitizeCitations, type ChatCardData, type ChatMessage } from "@/lib/api/chat";

import type { SecurityCheck } from "@/lib/api/security";

import type { UiMessage } from "./types";

function isCard(v: unknown): v is ChatCardData {
  return typeof v === "object" && v !== null && "card_type" in v;
}

function isSecurity(v: unknown): v is SecurityCheck {
  return typeof v === "object" && v !== null && Array.isArray((v as { checked?: unknown }).checked);
}

/** Rebuild the transcript from persisted rows: tool cards attach to the assistant answer that follows. */
export function rebuildMessages(rows: readonly ChatMessage[]): UiMessage[] {
  const out: UiMessage[] = [];
  let pending: ChatCardData[] = [];
  let lastUser: string | null = null;
  for (const m of [...rows].sort((a, b) => a.seq - b.seq)) {
    if (m.role === "user") {
      pending = [];
      lastUser = m.content;
      out.push({ id: m.id, role: "user", text: m.content });
    } else if (m.role === "tool") {
      if (isCard(m.card)) pending.push(m.card);
    } else {
      const meta = (m.meta ?? {}) as Record<string, unknown>;
      const fb = meta.feedback as { rating?: string } | undefined;
      const notes = Array.isArray(meta.notes)
        ? meta.notes.filter((n): n is string => typeof n === "string")
        : [];
      const aborted = Boolean(meta.aborted) && m.content.trim() === "";
      out.push({
        id: m.id,
        role: "assistant",
        text: m.content,
        why: typeof meta.why === "string" ? meta.why : null,
        notes,
        cards: pending,
        citations: sanitizeCitations(meta.citations),
        tools: [],
        status: aborted ? "interrupted" : "done",
        error: null,
        messageId: m.id,
        feedback: fb?.rating === "up" || fb?.rating === "down" ? fb.rating : null,
        stopped: null,
        retryText: aborted ? lastUser : null,
        security: isSecurity(meta.security) ? meta.security : null,
      });
      pending = [];
    }
  }
  return out;
}
