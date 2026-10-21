import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { I18nProvider, messages, useT } from "@/i18n";

import { LanguageToggle } from "./LanguageToggle";

function Probe() {
  const t = useT();
  return <p>{t("analysis.kpi.landedCost")}</p>;
}

describe("LanguageToggle", () => {
  it("switches labels to Bangla and updates <html lang>", () => {
    render(
      <I18nProvider>
        <LanguageToggle />
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByText("Landed cost")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("বাংলা"));
    expect(screen.getByText("ল্যান্ডেড কস্ট")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("bn");
    expect(document.cookie).toContain("setu_lang=bn");
  });

  it("has the same keys in en and bn", () => {
    expect(Object.keys(messages.bn).sort()).toEqual(
      Object.keys(messages.en).sort(),
    );
  });
});
