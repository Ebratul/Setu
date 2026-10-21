export type OnboardState = { dismissed: boolean; visited: string[] };
export type OnboardItemId = "orders" | "cashflow" | "demo";

export const ONBOARD_EVENT = "setu-onboard";
const EMPTY: OnboardState = { dismissed: false, visited: [] };

const memory = new Map<string, OnboardState>();
const keyFor = (userId: string) => `setu_onboard:${userId}`;

export function readOnboard(userId: string): OnboardState {
  try {
    const raw = localStorage.getItem(keyFor(userId));
    if (!raw) return memory.get(userId) ?? EMPTY;
    const v = JSON.parse(raw) as Partial<OnboardState>;
    return {
      dismissed: v.dismissed === true,
      visited: Array.isArray(v.visited) ? v.visited.filter((x): x is string => typeof x === "string") : [],
    };
  } catch {
    return memory.get(userId) ?? EMPTY;
  }
}

export function writeOnboard(userId: string, state: OnboardState) {
  memory.set(userId, state);
  try {
    localStorage.setItem(keyFor(userId), JSON.stringify(state));
  } catch {
    /* storage unavailable: state lives for this page view only */
  }
  window.dispatchEvent(new Event(ONBOARD_EVENT));
}

/** Pathname prefix that counts as "visited" for each checklist item. */
export const ONBOARD_PREFIX: Record<OnboardItemId, readonly string[]> = {
  orders: ["/app/deals", "/app/orders"],
  cashflow: ["/app/cashflow"],
  demo: ["/demo/attack-console", "/demo/scam-simulator"],
};

export function markVisited(userId: string, id: OnboardItemId) {
  const s = readOnboard(userId);
  if (s.visited.includes(id)) return;
  writeOnboard(userId, { ...s, visited: [...s.visited, id] });
}

/** Called on every navigation; ticks any checklist item whose page was opened. */
export function trackVisit(userId: string, pathname: string, role: string | undefined) {
  for (const id of Object.keys(ONBOARD_PREFIX) as OnboardItemId[]) {
    if (id === "demo") {
      const wanted = role === "ADMIN" || role === "JUDGE" ? "/demo/attack-console" : "/demo/scam-simulator";
      if (pathname.startsWith(wanted)) markVisited(userId, id);
    } else if (ONBOARD_PREFIX[id].some((p) => pathname.startsWith(p))) {
      markVisited(userId, id);
    }
  }
}
