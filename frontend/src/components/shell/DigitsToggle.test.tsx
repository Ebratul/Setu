import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { formatMoney, getDigits, setDigits } from "@/lib/format";

import { DigitsToggle } from "./DigitsToggle";
import { renderI18n, setLang } from "./testUtils";

beforeEach(() => localStorage.clear());
afterEach(() => act(() => setDigits("native")));

describe("DigitsToggle", () => {
  it("is hidden unless the language is Bangla", () => {
    setLang("en");
    renderI18n(<DigitsToggle />);
    expect(screen.queryByTestId("digits-toggle")).toBeNull();
  });

  it("switches Bangla numbers to Latin digits and back", () => {
    setLang("bn");
    renderI18n(<DigitsToggle />);
    const btn = screen.getByTestId("digits-toggle");
    expect(btn).toHaveAttribute("aria-pressed", "true");
    expect(formatMoney("1200", "BDT", "bn")).toBe("৳১,২০০.০০");
    fireEvent.click(btn);
    expect(getDigits()).toBe("latin");
    expect(btn).toHaveAttribute("aria-pressed", "false");
    expect(formatMoney("1200", "BDT", "bn")).toBe("৳1,200.00");
    expect(localStorage.getItem("setu_digits")).toBe("latin");
    fireEvent.click(btn);
    expect(getDigits()).toBe("native");
  });
});
