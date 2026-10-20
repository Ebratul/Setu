import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";
import type { ScoreItem } from "@/lib/api/demo";

import { Scorecard } from "./Scorecard";

const item = (id: string, group: ScoreItem["group"], ticked: boolean): ScoreItem => ({
  id,
  group,
  label: { en: `Label ${id}`, bn: `বাংলা ${id}` },
  link: `/app/${id}`,
  after: "1.1",
  ticked,
});

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

describe("Scorecard", () => {
  it("groups items in three sections, ticks with text, and links to the proving screen", () => {
    render(
      <I18nProvider>
        <Scorecard items={[item("a", "TASK", true), item("b", "SECURITY", false), item("c", "INNOVATION", true)]} />
      </I18nProvider>,
    );
    expect(screen.getByRole("heading", { name: "Task completion" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Security & compliance" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Innovation & interaction" })).toBeInTheDocument();
    expect(screen.getByTestId("score-count")).toHaveTextContent("2 of 3");
    const a = screen.getByRole("link", { name: /Label a/ });
    expect(a).toHaveAttribute("href", "/app/a");
    expect(within(a.closest("li")!).getByText(/Shown/)).toBeInTheDocument();
    expect(within(screen.getByRole("link", { name: /Label b/ }).closest("li")!).getByText(/Not shown yet/)).toBeInTheDocument();
  });
});
