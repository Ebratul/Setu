import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import type { PipelineStep, Scoreboard, SecurityCheck } from "@/lib/api/security";

import { HighlightedText, splitHighlights } from "./HighlightedText";
import { ScoreboardView } from "./InjectionScoreboard";
import { PipelineSteps } from "./PipelineSteps";
import { SecurityCheckChip } from "./SecurityCheckChip";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

const wrap = (ui: React.ReactElement) => render(<I18nProvider>{ui}</I18nProvider>);

function step(id: PipelineStep["id"], layer: number, ok: boolean, status: PipelineStep["status"]): PipelineStep {
  return { id, layer, ok, status, title_en: `T-${id}`, title_bn: `B-${id}`, detail_en: `D-${id}`, detail_bn: `BD-${id}` };
}
const ids: PipelineStep["id"][] = ["privacy", "wrap", "detector", "gating", "risk", "answer"];

describe("PipelineSteps", () => {
  it("renders six steps in order with check labels", () => {
    const steps = ids.map((id, i) => step(id, i, true, "done")).reverse();
    wrap(<PipelineSteps steps={steps} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(6);
    expect(items.map((li) => li.getAttribute("data-testid"))).toEqual(ids.map((i) => `step-${i}`));
    expect(screen.getAllByLabelText("Handled safely")).toHaveLength(6);
  });

  it("shows a cross for the detector when defences are off", () => {
    const steps = ids.map((id) => (id === "detector" ? step(id, 2, false, "off") : step(id, 1, true, "done")));
    wrap(<PipelineSteps steps={steps} />);
    const det = screen.getByTestId("step-detector");
    expect(within(det).getByLabelText("Not stopped here")).toHaveTextContent("✕");
    expect(within(det).getByText("Layer 2")).toBeInTheDocument();
  });
});

describe("HighlightedText", () => {
  it("highlights ranges and clamps out-of-range ones", () => {
    wrap(
      <HighlightedText
        text="hello ignore previous world"
        highlights={[
          { start: 6, end: 21, rule: "EN_IGNORE" },
          { start: 22, end: 999, rule: "TAIL" },
          { start: -5, end: -1, rule: "NONE" },
        ]}
      />,
    );
    const marks = document.querySelectorAll("mark");
    expect(marks).toHaveLength(2);
    expect(marks[0]).toHaveAttribute("data-rule", "EN_IGNORE");
    expect(marks[0].textContent).toContain("ignore previous");
    expect(marks[1].textContent).toContain("world");
  });

  it("never repeats characters on overlap and renders markup inert", () => {
    const text = "<b>x</b>abcdef";
    const pieces = splitHighlights(text, [
      { start: 8, end: 12, rule: "A" },
      { start: 10, end: 14, rule: "B" },
    ]);
    expect(pieces.map((p) => p.text).join("")).toBe(text);
    wrap(<HighlightedText text={text} highlights={[]} />);
    expect(document.querySelector("b")).toBeNull();
  });
});

describe("SecurityCheckChip", () => {
  const sec: SecurityCheck = {
    defences: true,
    checked: ["check_documents", "search_knowledge"],
    ignored: [{ source: "hidden_text", rules: ["EN_IGNORE"], score: 0.9 }],
    blocked_tools: [{ name: "propose_release_tranche", code: "GATED" }],
    deal_flagged: true,
    guard: [],
  };

  it("renders nothing when security is null", () => {
    wrap(<SecurityCheckChip security={null} />);
    expect(screen.queryByTestId("security-chip")).toBeNull();
  });

  it("expands and lists checked, ignored, blocked and flagged", () => {
    wrap(<SecurityCheckChip security={sec} />);
    const btn = screen.getByRole("button", { name: /Security check/ });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Checked: documents, knowledge base/)).toBeInTheDocument();
    expect(screen.getByText(/Ignored a hidden instruction in a document/)).toBeInTheDocument();
    expect(screen.getByText("Blocked: propose_release_tranche")).toBeInTheDocument();
    expect(screen.getByText(/Deal flagged for extra verification/)).toBeInTheDocument();
  });
});

describe("ScoreboardView", () => {
  const stats = (rate: number) => ({
    n: 40,
    attack_success_rate: rate,
    forbidden_attempts: 0,
    reached_services: 0,
    answers_that_followed: 0,
    detected: 0,
    money_moved: 0,
    per_style: {},
  });
  const data: Scoreboard = {
    simulated: true,
    available: true,
    split: "dev",
    generated_at: "2026-10-19T10:00:00Z",
    attacks: 40,
    modes: { off: stats(0.5), on: stats(0), on_without_detector: stats(0.125) },
    detection: { recall: 0.95, end_to_end_recall: 0.9, clean_documents: 20, false_positives: 1, false_positive_rate: 0.05 },
    layer_attribution: {},
    notes: "",
  };

  it("shows bar values and a table alternative", () => {
    wrap(<ScoreboardView data={data} onRerun={() => {}} running={false} />);
    const vals = screen.getAllByTestId("sb-bar").map((b) => b.getAttribute("data-value"));
    expect(vals).toEqual(["0.5", "0", "0.125", "0.95", "0.05"]);
    expect(screen.getByTestId("sb-table")).toBeInTheDocument();
    expect(screen.getAllByText(/layers 4\+5 only/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Test-split numbers are reported separately/)).toBeInTheDocument();
  });

  it("offers to run the suite when unavailable and calls rerun", () => {
    const onRerun = vi.fn();
    wrap(<ScoreboardView data={{ ...data, available: false }} onRerun={onRerun} running={false} />);
    expect(screen.getByTestId("sb-empty")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run the suite" }));
    expect(onRerun).toHaveBeenCalled();
  });

  it("disables the button while running", () => {
    wrap(<ScoreboardView data={data} onRerun={() => {}} running />);
    expect(screen.getByRole("button", { name: "Running the suite…" })).toBeDisabled();
  });
});
