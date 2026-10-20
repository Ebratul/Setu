import type { DemoRun, DemoSandbox, DemoScript, SceneResult } from "@/lib/api/demo";

const bi = (en: string) => ({ en, bn: `${en} (bn)` });

export const SCRIPT: DemoScript = {
  simulated: true,
  total_scenes: 4,
  scorecard: [],
  steps: [
    {
      n: 1,
      id: "a",
      tag: "INNOVATION",
      title: bi("Ask in Bangla"),
      narration: bi("Rahima asks."),
      notes: bi("Open with the person."),
      scenes: [{ k: 1, view: "buyer", login_as: "rahima@demo.setu", route: "/app/chat", highlight: '[data-demo="chat-answer"]', caption: bi("Answer in Bangla") }],
    },
    {
      n: 2,
      id: "b",
      tag: "TASK",
      title: bi("Landed cost"),
      narration: bi("The order costs."),
      notes: bi("Point at the number."),
      scenes: [
        { k: 1, view: "buyer", login_as: "rahima@demo.setu", route: "/app/orders/{deal.ref}/analysis", highlight: '[data-demo="landed-cost"]', caption: bi("Landed cost") },
        { k: 2, view: "supplier", login_as: "huaxin@demo.setu", route: "/supplier/{deal.id}", highlight: '[data-demo="supplier-schedule"]', caption: bi("Supplier view") },
      ],
    },
    {
      n: 3,
      id: "c",
      tag: "SECURITY",
      title: bi("Forged B/L"),
      narration: bi("A forged document."),
      notes: bi("Reveal the hidden text."),
      scenes: [{ k: 1, view: "buyer", login_as: "rahima@demo.setu", route: "/app/documents/{forged.id}", highlight: '[data-demo="hidden-text"]', caption: bi("Hidden text") }],
    },
  ],
};

export const SANDBOX: DemoSandbox = {
  simulated: true,
  id: "11111111-1111-4111-8111-111111111111",
  created_at: "2026-10-20T05:00:00Z",
  expires_at: "2026-10-20T09:00:00Z",
  replay: true,
  live_ai: false,
  live_ai_available: false,
  live_ai_budget_left: 25,
  resets: 0,
};

export const passed = (n: number, k: number, route: string, extra: Partial<SceneResult> = {}): SceneResult => ({
  n,
  k,
  status: "passed",
  route,
  assertions: [],
  facts: {},
  ...extra,
});

export const emptyRun = (over: Partial<DemoRun> = {}): DemoRun => ({
  sandbox: SANDBOX,
  cursor: null,
  scenes: [],
  scorecard: [],
  total_scenes: 4,
  passed: 0,
  failed: 0,
  completed: false,
  last: null,
  ...over,
});
