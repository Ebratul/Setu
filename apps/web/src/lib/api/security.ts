import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type GalleryItem = S["GalleryOut"];
export type ConsoleRunIn = S["ConsoleRunIn"];
export type ConsoleRunOut = S["ConsoleRunOut"];
export type PipelineStep = S["Step"];
export type ToolAttempt = S["ToolAttempt"];
export type Detection = S["DetectionOut"];
export type Highlight = S["Highlight"];
export type Scoreboard = S["ScoreboardOut"];
export type ModeStats = S["ModeStats"];
export type InjectionEvent = S["InjectionEventOut"];
export type InjectionEventList = S["InjectionEventList"];
export type SecurityCheck = S["SecurityCheckOut"];
export type InjectionFinding = S["InjectionFindingOut"];
export type AttackSource = ConsoleRunIn["source"];

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export const getGallery = (signal?: AbortSignal) =>
  apiGet<S["GalleryList"]>("/security/injection/gallery", opts(signal));

export const runAttack = (body: Partial<ConsoleRunIn>, signal?: AbortSignal) =>
  apiPost<ConsoleRunOut>("/security/injection/run", body, { signal });

export const getScoreboard = (signal?: AbortSignal) =>
  apiGet<Scoreboard>("/security/injection/scoreboard", opts(signal));

export const rerunScoreboard = (signal?: AbortSignal) =>
  apiPost<Scoreboard>("/security/injection/scoreboard/rerun", undefined, { signal });

export type EventFilter = { style?: string; source?: string; origin?: string; limit?: number };

export function getInjectionEvents(f: EventFilter, signal?: AbortSignal) {
  const q = new URLSearchParams();
  if (f.style) q.set("style", f.style);
  if (f.source) q.set("source", f.source);
  if (f.origin) q.set("origin", f.origin);
  q.set("limit", String(f.limit ?? 100));
  return apiGet<InjectionEventList>(`/security/injection/events?${q}`, opts(signal));
}

export const resolveInjectionEvent = (id: string, signal?: AbortSignal) =>
  apiPost<InjectionEvent>(`/security/injection/events/${encodeURIComponent(id)}/resolve`, undefined, { signal });
