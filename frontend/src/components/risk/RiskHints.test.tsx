import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";

import { RiskHints } from "./RiskHints";

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

describe("RiskHints", () => {
  it("shows the target tier and styles blocked hints neutrally", () => {
    render(
      <I18nProvider>
        <RiskHints
          hints={[
            { code: "A", to_tier: 2, text_en: "Use smaller tranches", text_bn: "x" },
            { code: "B", to_tier: null, text_en: "Resolve the sanctions hit", text_bn: "y" },
          ]}
        />
      </I18nProvider>,
    );
    expect(screen.getByText("What would lower the risk?")).toBeInTheDocument();
    expect(screen.getByTestId("hint-A")).toHaveTextContent("→ Tier 2");
    expect(screen.getByTestId("hint-B")).not.toHaveTextContent("→ Tier");
    expect(screen.getByTestId("hint-B")).toHaveTextContent("Cannot be lowered here");
  });

  it("renders nothing without hints", () => {
    const { container } = render(
      <I18nProvider>
        <RiskHints hints={[]} />
      </I18nProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
