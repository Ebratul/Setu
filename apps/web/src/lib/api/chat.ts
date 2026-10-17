import { readSse } from "@/lib/sse";

import type { components } from "./schema.gen";
import { ApiError, apiGet, apiPost } from "./client";

type S = components["schemas"];
export type ChatResponse = S["ChatResponse"];
export type ChatMessage = S["MessageOut"];
export type ChatThread = S["ThreadOut"];
export type ChatCardData = NonNullable<ChatResponse["cards"]>[number];
export type Citation = components["schemas"]["Citation"];
export type CardType = ChatCardData["card_type"];
export type ChatLanguage = "en" | "bn";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export type ChatRequest = {
  thread_id?: string;
  message: string;
  language?: ChatLanguage;
  deal_id?: string;
};

export type StreamEvent =
  | {
      type: "meta";
      thread_id: string | null;
      intent: string | null;
      model: string | null;
      language: string;
    }
  | { type: "tool_start"; name: string; id: string }
  | {
      type: "tool_end";
      name: string;
      id: string;
      ok: boolean;
      error_code: string | null;
      card: ChatCardData | null;
    }
  | { type: "token"; text: string }
  | { type: "final"; response: ChatResponse }
  | { type: "error"; code: string; message: string };

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const isUuid = (v: unknown): v is string =>
  typeof v === "string" && UUID.test(v);

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isArr = (v: unknown): v is unknown[] => Array.isArray(v);
const str = (v: unknown, d = ""): string => (typeof v === "string" ? v : d);

function validSide(v: unknown): boolean {
  return isObj(v) && isArr(v.series);
}

/** Shape-check a card before rendering; returns null for unknown or malformed cards. */
export function validateCard(v: unknown): ChatCardData | null {
  if (!isObj(v) || !isObj(v.data) || typeof v.card_type !== "string") return null;
  if (typeof v.explanation_en !== "string" || typeof v.explanation_bn !== "string") {
    return null;
  }
  const d = v.data;
  let ok = false;
  switch (v.card_type) {
    case "landed_cost":
      ok = isArr(d.lines) && typeof d.landed_cost === "string";
      break;
    case "cashflow":
      ok = validSide(d.before) && isArr(d.upcoming) && (d.after == null || validSide(d.after));
      break;
    case "alerts":
      ok = isArr(d.alerts);
      break;
    case "financing_comparison":
      ok = isArr(d.options) && d.options.every(isObj);
      break;
    case "fx_compare":
      ok = isObj(d.usd_route) && isObj(d.cny_route) && isArr(d.assumptions);
      break;
    case "monthly_summary":
      ok = isArr(d.history) && isArr(d.insights);
      break;
    case "scorecard":
      ok = isArr(d.suppliers);
      break;
    case "kyb":
      ok =
        typeof d.supplier_name === "string" &&
        typeof d.status === "string" &&
        ["VERIFIED", "WARNING", "BLOCKED"].includes(d.status) &&
        isArr(d.reasons) &&
        d.reasons.every(isObj);
      break;
    case "citations":
      ok = isArr(d.snippets) && isArr(d.withheld);
      break;
  }
  return ok ? (v as unknown as ChatCardData) : null;
}

/** Keep only well-formed citation objects (all string fields). */
export function sanitizeCitations(v: unknown): Citation[] {
  if (!isArr(v)) return [];
  const keys = ["cite_id", "source_id", "title", "heading_path", "source_type", "original_reference", "last_reviewed", "disclaimer"] as const;
  const out: Citation[] = [];
  for (const c of v) {
    if (!isObj(c) || !/^S\d+$/.test(str(c.cite_id))) continue;
    const item = {} as Record<string, string>;
    for (const k of keys) item[k] = str(c[k]);
    out.push(item as unknown as Citation);
  }
  return out;
}

function validCards(v: unknown): ChatCardData[] {
  return isArr(v)
    ? v.map(validateCard).filter((c): c is ChatCardData => c !== null)
    : [];
}

export function parseEvent(name: string, data: string): StreamEvent | null {
  let json: unknown;
  try {
    json = JSON.parse(data);
  } catch {
    return null;
  }
  if (!isObj(json)) return null;
  switch (name) {
    case "meta":
      return {
        type: "meta",
        thread_id: isUuid(json.thread_id) ? json.thread_id : null,
        intent: typeof json.intent === "string" ? json.intent : null,
        model: typeof json.model === "string" ? json.model : null,
        language: str(json.language),
      };
    case "tool_start":
      return { type: "tool_start", name: str(json.name), id: str(json.id) };
    case "tool_end":
      return {
        type: "tool_end",
        name: str(json.name),
        id: str(json.id),
        ok: json.ok === true,
        error_code: typeof json.error_code === "string" ? json.error_code : null,
        card: validateCard(json.card),
      };
    case "token":
      return { type: "token", text: str(json.text) };
    case "final": {
      if (typeof json.answer !== "string" || !isUuid(json.thread_id)) return null;
      const response = {
        ...json,
        cards: validCards(json.cards),
        citations: sanitizeCitations(json.citations),
        notes: isArr(json.notes) ? json.notes.filter((n) => typeof n === "string") : [],
        why: typeof json.why === "string" ? json.why : null,
        message_id: isUuid(json.message_id) ? json.message_id : "",
      } as unknown as ChatResponse;
      return { type: "final", response };
    }
    case "error":
      return {
        type: "error",
        code: str(json.code, "error"),
        message: str(json.message),
      };
    default:
      return null;
  }
}

/** POST /chat/stream and yield typed events. Non-2xx responses throw ApiError before any event. */
export async function* streamChat(
  body: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail: string | null = null;
    try {
      const j: unknown = await res.json();
      const d = (j as { detail?: unknown }).detail;
      detail = typeof d === "string" ? d : null;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, `POST /chat/stream failed with ${res.status}`, detail);
  }
  for await (const raw of readSse(res.body)) {
    const ev = parseEvent(raw.event, raw.data);
    if (ev) yield ev;
  }
}

function checkId(id: string): string {
  if (!isUuid(id)) throw new ApiError(400, "invalid id");
  return encodeURIComponent(id);
}

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export const listThreads = (q: string, signal?: AbortSignal) =>
  apiGet<{ threads: ChatThread[] }>(
    `/chat/threads${q ? `?q=${encodeURIComponent(q)}` : ""}`,
    opts(signal),
  );

export const getThreadMessages = (id: string, signal?: AbortSignal) =>
  apiGet<{ thread_id: string; messages: ChatMessage[] }>(
    `/chat/threads/${checkId(id)}/messages`,
    opts(signal),
  );

async function send<T>(method: "PATCH" | "DELETE", path: string, body?: unknown) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "same-origin",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, `${method} ${path} failed with ${res.status}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const renameThread = (id: string, title: string) =>
  send<ChatThread>("PATCH", `/chat/threads/${checkId(id)}`, { title });

export const deleteThread = (id: string) =>
  send<void>("DELETE", `/chat/threads/${checkId(id)}`);

export const sendFeedback = (messageId: string, rating: "up" | "down") =>
  apiPost<S["FeedbackOut"]>(
    `/chat/messages/${checkId(messageId)}/feedback`,
    { rating },
  );
