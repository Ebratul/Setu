/** Returns a score (higher is better) or null when `query` does not match `text`. Substring beats subsequence. */
export function fuzzyScore(query: string, text: string): number | null {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const s = text.toLowerCase();
  const at = s.indexOf(q);
  if (at !== -1) return 1000 - at - (s.length - q.length) * 0.01;
  let i = 0;
  let gaps = 0;
  let last = -1;
  for (const ch of q) {
    if (ch === " ") continue;
    const next = s.indexOf(ch, i);
    if (next === -1) return null;
    if (last !== -1 && next !== last + 1) gaps++;
    last = next;
    i = next + 1;
  }
  return 500 - gaps * 10 - s.length * 0.01;
}
