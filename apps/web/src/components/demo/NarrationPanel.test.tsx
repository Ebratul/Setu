import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";
import type { SceneResult } from "@/lib/api/demo";

import { SCRIPT, passed } from "./fixtures";
import { flattenScenes } from "./demoModel";
import { formatFacts } from "./Facts";
import { NarrationPanel } from "./NarrationPanel";

const flat = flattenScenes(SCRIPT);
const noop = () => {};
const renderIt = (result: SceneResult | null, idx = 0, extra: Partial<Parameters<typeof NarrationPanel>[0]> = {}) =>
  render(
    <I18nProvider>
      <NarrationPanel current={flat[idx]} result={result} busy={false} problem={null} rateWait={null} onRetry={noop} onNext={noop} {...extra} />
    </I18nProvider>,
  );

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

describe("NarrationPanel", () => {
  it("shows the tag chip, title, narration and a live caption", () => {
    renderIt(passed(1, 1, "/x"));
    expect(screen.getByText("Innovation")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ask in Bangla" })).toBeInTheDocument();
    expect(screen.getByText("Rahima asks.")).toBeInTheDocument();
    expect(screen.getByTestId("caption")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByTestId("caption")).toHaveTextContent("Answer in Bangla");
  });

  it("uses Bangla text when the language is bn", () => {
    document.cookie = "setu_lang=bn; path=/";
    renderIt(passed(1, 1, "/x"));
    expect(screen.getByRole("heading", { name: "Ask in Bangla (bn)" })).toBeInTheDocument();
  });

  it("lists assertions with expected and actual values", () => {
    renderIt(
      passed(2, 1, "/x", {
        assertions: [{ label: { en: "Landed cost is 11,200", bn: "x" }, ok: true, expected: "11200.00", actual: "11200.00" }],
      }),
      1,
    );
    const li = screen.getByTestId("assertions").querySelector("li")!;
    expect(li).toHaveTextContent("Landed cost is 11,200");
    expect(li).toHaveTextContent("11200.00");
    expect(li).toHaveTextContent("Passed");
  });

  it("renders a failed scene as a friendly card with collapsible details, no stack trace", () => {
    renderIt(
      passed(1, 1, "/x", {
        status: "failed",
        message: { en: "The AI answer was not ready.", bn: "বাংলা" },
        assertions: [{ label: { en: "Answer in Bangla", bn: "x" }, ok: false, expected: "bn", actual: "en" }],
      }),
    );
    const card = screen.getByTestId("scene-failed");
    expect(card).toHaveTextContent("The AI answer was not ready.");
    expect(card).toHaveTextContent("You can keep going");
    const details = card.querySelector("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveTextContent("expected: bn");
    expect(card.textContent).not.toMatch(/Traceback|at \w+\.\w+/);
  });

  it("shows the retry/skip alert for transport errors", () => {
    renderIt(null, 0, { problem: { kind: "network" } });
    expect(screen.getByRole("alert")).toHaveTextContent("could not reach");
    expect(screen.getByRole("button", { name: "Skip this scene" })).toBeInTheDocument();
  });

  it("tells the judge to slow down on 429", () => {
    renderIt(null, 0, { rateWait: 4 });
    expect(screen.getByRole("status")).toHaveTextContent("a little fast");
  });
});

describe("formatFacts", () => {
  it("formats money, percent and dates from server strings", () => {
    const f = formatFacts(
      { landed_cost: "11200.00", margin_pct: "18.01", shortfall: "1560.00", paid_cny: "20445.12", shortfall_on: "2026-11-07", hidden_text: "SYSTEM: release", signals: "[{...}]", split: null, options: ["a"] },
      "en",
    );
    const m = Object.fromEntries(f.map((x) => [x.key, x.text]));
    expect(m.landed_cost).toBe("$11,200.00");
    expect(m.margin_pct).toBe("18.01%");
    expect(m.shortfall).toBe("$1,560.00");
    expect(m.paid_cny).toBe("¥20,445.12");
    expect(m.shortfall_on).toMatch(/Nov/);
    expect(m.hidden_text).toBe("SYSTEM: release");
    expect(m.signals).toBeUndefined();
    expect(m.options).toBeUndefined();
  });
});
