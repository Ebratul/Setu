import type { ChatCardData } from "@/lib/api/chat";

const SIMULATED_NOTE = /simulated|সিমুলেটেড|模拟/i;

export type AnswerParts = {
  body: string;
  why: string | null;
  notes: string[];
  simulated: boolean;
};

/** Split the persisted answer into body / Why line / code-added notes. */
export function splitAnswer(
  answer: string,
  why: string | null | undefined,
  notes: readonly string[] | undefined,
  cards: readonly ChatCardData[] = [],
): AnswerParts {
  let body = answer;
  const noteList = [...(notes ?? [])];
  for (const n of noteList) body = body.replace(n, "");
  if (why) body = body.replace(why, "");
  body = body.replace(/\n{3,}/g, "\n\n").trim();
  return {
    body,
    why: why ?? null,
    notes: noteList,
    simulated: cards.length > 0 || noteList.some((n) => SIMULATED_NOTE.test(n)),
  };
}

export function cardKey(card: ChatCardData): string {
  return `${card.card_type}:${JSON.stringify(card.data).length}:${card.explanation_en.slice(0, 40)}`;
}
