import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HERO_CYCLE_MS, HeroPreview } from "./HeroPreview";

describe("HeroPreview", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("cycles through the three states every 5 seconds", () => {
    render(<HeroPreview />);
    expect(screen.getByTestId("hero-caption")).toHaveTextContent(/Cash-flow alert/);
    act(() => vi.advanceTimersByTime(HERO_CYCLE_MS));
    expect(screen.getByTestId("hero-caption")).toHaveTextContent(/Tier 3 release/);
    act(() => vi.advanceTimersByTime(HERO_CYCLE_MS));
    expect(screen.getByTestId("hero-caption")).toHaveTextContent(/Forged bill of lading/);
    act(() => vi.advanceTimersByTime(HERO_CYCLE_MS));
    expect(screen.getByTestId("hero-caption")).toHaveTextContent(/Cash-flow alert/);
  });

  it("pauses on the pause button and switches state with the tab buttons", () => {
    render(<HeroPreview />);
    fireEvent.click(screen.getByRole("button", { name: "Pause preview" }));
    act(() => vi.advanceTimersByTime(HERO_CYCLE_MS * 3));
    expect(screen.getByTestId("hero-caption")).toHaveTextContent(/Cash-flow alert/);
    fireEvent.click(screen.getByRole("button", { name: "Forgery blocked" }));
    expect(screen.getByRole("button", { name: "Forgery blocked" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("hero-caption")).toHaveTextContent(/Forged bill of lading/);
  });

  it("pauses while hovered and keeps the mock out of the accessibility tree", () => {
    const { container } = render(<HeroPreview />);
    fireEvent.mouseEnter(container.querySelector("section")!);
    act(() => vi.advanceTimersByTime(HERO_CYCLE_MS * 2));
    expect(screen.getByTestId("hero-caption")).toHaveTextContent(/Cash-flow alert/);
    expect(container.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });

  it("does not auto-advance and hides the pause button under reduced motion", () => {
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: true,
      media: q,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    render(<HeroPreview />);
    act(() => vi.advanceTimersByTime(HERO_CYCLE_MS * 2));
    expect(screen.getByTestId("hero-caption")).toHaveTextContent(/Cash-flow alert/);
    expect(screen.queryByRole("button", { name: "Pause preview" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Approval with OTP" }));
    expect(screen.getByTestId("hero-caption")).toHaveTextContent(/Tier 3 release/);
    vi.unstubAllGlobals();
  });
});
