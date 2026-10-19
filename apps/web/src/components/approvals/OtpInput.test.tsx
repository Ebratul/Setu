import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";

import { OtpInput } from "./OtpInput";

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

function Host({ initial = "" }: { initial?: string }) {
  const [v, setV] = useState(initial);
  return (
    <I18nProvider>
      <OtpInput value={v} onChange={setV} label="6-digit code" />
      <output data-testid="value">{v}</output>
    </I18nProvider>
  );
}
const box = (n: number) => screen.getByLabelText(`Digit ${n} of 6`) as HTMLInputElement;

describe("OtpInput", () => {
  it("has six numeric, labelled boxes", () => {
    render(<Host />);
    expect(screen.getByRole("group", { name: "6-digit code" })).toBeInTheDocument();
    for (let i = 1; i <= 6; i++) expect(box(i)).toHaveAttribute("inputmode", "numeric");
  });

  it("advances focus after each digit", () => {
    render(<Host />);
    fireEvent.change(box(1), { target: { value: "4" } });
    expect(document.activeElement).toBe(box(2));
    fireEvent.change(box(2), { target: { value: "2" } });
    expect(screen.getByTestId("value")).toHaveTextContent("42");
    expect(document.activeElement).toBe(box(3));
  });

  it("spreads a pasted code across the boxes and ignores non-digits", () => {
    render(<Host />);
    fireEvent.paste(box(1), { clipboardData: { getData: () => " 123-456 " } });
    expect(screen.getByTestId("value")).toHaveTextContent("123456");
    expect(box(6).value).toBe("6");
    expect(document.activeElement).toBe(box(6));
  });

  it("backspace on an empty box clears and focuses the previous one", () => {
    render(<Host initial="12" />);
    box(3).focus();
    fireEvent.keyDown(box(3), { key: "Backspace" });
    expect(screen.getByTestId("value")).toHaveTextContent(/^1$/);
    expect(document.activeElement).toBe(box(2));
  });
});
