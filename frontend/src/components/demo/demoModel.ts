import type { Bi, DemoScene, DemoScript, DemoStep, SceneResult } from "@/lib/api/demo";

export type FlatScene = {
  index: number;
  n: number;
  k: number;
  key: string;
  step: DemoStep;
  scene: DemoScene;
  /** 1-based position inside the step, and the step's scene count. */
  pos: number;
  count: number;
};

export const sceneKey = (n: number, k: number) => `${n}.${k}`;

/** Steps to one ordered scene list; the scene is the navigation unit. */
export function flattenScenes(script: Pick<DemoScript, "steps">): FlatScene[] {
  const out: FlatScene[] = [];
  for (const step of script.steps) {
    step.scenes.forEach((scene, i) => {
      out.push({
        index: out.length,
        n: step.n,
        k: scene.k,
        key: sceneKey(step.n, scene.k),
        step,
        scene,
        pos: i + 1,
        count: step.scenes.length,
      });
    });
  }
  return out;
}

/** First scene of step `n` (deep link / jump); null when the step does not exist. */
export function indexForStep(flat: FlatScene[], n: number): number | null {
  const hit = flat.find((f) => f.n === n);
  return hit ? hit.index : null;
}

export function parseStepParam(raw: string | null, flat: FlatScene[]): number | null {
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return indexForStep(flat, n) === null ? null : n;
}

export const nextIndex = (flat: FlatScene[], i: number) => (i + 1 < flat.length ? i + 1 : null);
export const prevIndex = (i: number) => (i > 0 ? i - 1 : null);

/** "step 4 · 2/3" parts. */
export function progressOf(f: FlatScene) {
  return { step: f.n, pos: f.pos, count: f.count };
}

export const biText = (b: Bi | null | undefined, lang: string) => (b ? (lang === "bn" ? b.bn : b.en) : "");

export const BASE_DWELL_MS = 7000;
export const SPEEDS = [1, 1.5, 2] as const;
export type Speed = (typeof SPEEDS)[number];

/** Dwell per scene: base 7 s, +40 ms per character beyond 90, capped at 16 s, divided by speed. */
export function dwellMs(textLength: number, speed: number): number {
  const extra = Math.max(0, textLength - 90) * 40;
  const raw = Math.min(16000, BASE_DWELL_MS + extra);
  return Math.round(raw / (speed > 0 ? speed : 1));
}

export const isDone = (r: SceneResult | undefined) => r?.status === "passed" || r?.status === "failed";

export type DemoLang = "en" | "bn";
export const toDemoLang = (lang: string): DemoLang => (lang === "bn" ? "bn" : "en");

export type Mode = "normal" | "presenter" | "record";
export function parseMode(raw: string | null): Mode {
  return raw === "presenter" || raw === "record" ? raw : "normal";
}

export const ROLES = [
  { id: "buyer", email: "rahima@demo.setu" },
  { id: "supplier", email: "huaxin@demo.setu" },
  { id: "admin", email: "admin@demo.setu" },
] as const;

export function roleOfEmail(email: string | null): (typeof ROLES)[number]["id"] | null {
  return ROLES.find((r) => r.email === email)?.id ?? null;
}

/** Same-origin iframe URL for a resolved route, with `embed=1`. */
export function embedUrl(route: string): string {
  const [path, hash] = route.split("#");
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}embed=1${hash ? `#${hash}` : ""}`;
}

export function formatCountdown(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}
