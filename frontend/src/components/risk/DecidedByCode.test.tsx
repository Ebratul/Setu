import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";

import { DecidedByCode } from "./DecidedByCode";

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

describe("DecidedByCode", () => {
  it("opens an accessible tooltip on keyboard focus and closes on Escape", () => {
    render(
      <I18nProvider>
        <DecidedByCode />
      </I18nProvider>,
    );
    const btn = screen.getByRole("button", { name: /Decided by code, not by AI/ });
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.focus(btn);
    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent("The AI only explains");
    expect(tip).toHaveTextContent("cannot be changed by prompts, documents or the client");
    expect(btn).toHaveAttribute("aria-describedby", tip.id);
    fireEvent.keyDown(btn, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
