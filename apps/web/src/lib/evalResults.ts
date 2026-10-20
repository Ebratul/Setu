import { readFile } from "node:fs/promises";
import path from "node:path";

import { METRIC_IDS } from "./evalMetrics";

export { METRIC_IDS };

export type MetricId = (typeof METRIC_IDS)[number];
export type MetricUnit = "percent" | "count";
export type Metric = { value: number; total: number; unit: MetricUnit; source: string };

export type EvalResults = {
  split: "dev";
  synthetic: true;
  generatedAt: string;
  metrics: Record<MetricId, Metric | null>;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function parseMetric(v: unknown): Metric | null {
  if (!isRecord(v)) return null;
  const { value, total, unit, source } = v;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
  if (typeof total !== "number" || !Number.isInteger(total) || total <= 0) return null;
  if (unit !== "percent" && unit !== "count") return null;
  if (unit === "percent" && value > 1) return null;
  return { value, total, unit, source: typeof source === "string" ? source : "" };
}

/** Validates the JSON copy; returns null for anything that is not a dev-split file with at least one metric. Test-split data is never accepted. */
export function parseEvalResults(raw: unknown): EvalResults | null {
  if (!isRecord(raw) || raw.split !== "dev" || !isRecord(raw.metrics)) return null;
  const metrics = {} as Record<MetricId, Metric | null>;
  let present = 0;
  for (const id of METRIC_IDS) {
    const m = parseMetric(raw.metrics[id]);
    metrics[id] = m;
    if (m) present += 1;
  }
  if (present === 0) return null;
  const generatedAt = typeof raw.generatedAt === "string" ? raw.generatedAt : "";
  return { split: "dev", synthetic: true, generatedAt, metrics };
}

export async function loadEvalResults(): Promise<EvalResults | null> {
  try {
    const file = path.join(process.cwd(), "public", "eval-results.json");
    return parseEvalResults(JSON.parse(await readFile(file, "utf8")));
  } catch {
    return null;
  }
}
