import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";

import { risk } from "./fixtures";
import { RuleTrace } from "./RuleTrace";

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

const wrap = () =>
  render(
    <I18nProvider>
      <RuleTrace trace={risk().trace ?? []} />
    </I18nProvider>,
  );

describe("RuleTrace", () => {
  it("lists fired rules first and highlights the deciding one with a label", () => {
    wrap();
    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveAttribute("data-testid", "trace-AMOUNT_OVER_LIMIT");
    expect(rows[0]).toHaveAttribute("data-deciding", "true");
    expect(within(rows[0]).getByText("Set the final tier")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Amount USD 22,000 vs limit USD 20,000")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Tier 3")).toBeInTheDocument();
    const second = screen.getByTestId("trace-FIRST_DEAL");
    expect(second).toHaveAttribute("data-deciding", "false");
    expect(within(second).queryByText("Set the final tier")).toBeNull();
  });

  it("hides rules that did not fire behind a toggle", () => {
    wrap();
    expect(screen.queryByTestId("trace-SANCTIONS")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show 1 rules that did not fire" }));
    const row = screen.getByTestId("trace-SANCTIONS");
    expect(row).toHaveAttribute("data-fired", "false");
    expect(within(row).getByText("Did not fire")).toBeInTheDocument();
    expect(within(row).getByText("Block")).toBeInTheDocument();
  });

  it("switches to Bengali text", () => {
    document.cookie = "setu_lang=bn; path=/";
    wrap();
    expect(screen.getAllByText("পরিমাণ USD ২২,০০০, সীমা USD ২০,০০০").length).toBeGreaterThan(0);
  });
});
