import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";

import { KybBadge } from "./KybBadge";

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

describe("KybBadge", () => {
  it.each([
    ["VERIFIED", "Verified", "✓", "border-success"],
    ["WARNING", "Warning", "▲", "border-warning"],
    ["BLOCKED", "Blocked", "✕", "border-danger"],
  ] as const)("%s shows text, icon and an aria-label", (status, text, icon, cls) => {
    render(
      <I18nProvider>
        <KybBadge status={status} />
      </I18nProvider>,
    );
    const el = screen.getByTestId("kyb-badge");
    expect(el).toHaveTextContent(text);
    expect(el).toHaveTextContent(icon);
    expect(el).toHaveAttribute("aria-label", `Supplier check: ${text}`);
    expect(el.className).toContain(cls);
  });

  it("renders Bangla text when the language is bn", () => {
    document.cookie = "setu_lang=bn; path=/";
    render(
      <I18nProvider>
        <KybBadge status="BLOCKED" />
      </I18nProvider>,
    );
    expect(screen.getByTestId("kyb-badge")).toHaveTextContent("অবরুদ্ধ");
  });
});
