import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SLIDE_MS, Testimonials } from "./Testimonials";

const visible = () => screen.getAllByRole("group", { hidden: false }).filter((g) => !g.hasAttribute("hidden"));

describe("Testimonials", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("is a labelled carousel flagged as fictional personas", () => {
    const { container } = render(<Testimonials />);
    const carousel = container.querySelector('[aria-roledescription="carousel"]');
    expect(carousel).toHaveAccessibleName("Voices from the trade");
    expect(screen.getByText(/Fictional personas/)).toBeInTheDocument();
    expect(visible()).toHaveLength(1);
  });

  it("moves with prev, next and dots", () => {
    render(<Testimonials />);
    fireEvent.click(screen.getByRole("button", { name: "Next story" }));
    expect(visible()[0]).toHaveAccessibleName("2 of 3");
    fireEvent.click(screen.getByRole("button", { name: "Previous story" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous story" }));
    expect(visible()[0]).toHaveAccessibleName("3 of 3");
    fireEvent.click(screen.getByRole("button", { name: "Go to story 2" }));
    expect(visible()[0]).toHaveAccessibleName("2 of 3");
    expect(screen.getByRole("button", { name: "Go to story 2" })).toHaveAttribute("aria-current", "true");
  });

  it("auto-advances, and stops on pause or hover", () => {
    const { container } = render(<Testimonials />);
    act(() => vi.advanceTimersByTime(SLIDE_MS));
    expect(visible()[0]).toHaveAccessibleName("2 of 3");
    fireEvent.click(screen.getByRole("button", { name: "Pause stories" }));
    act(() => vi.advanceTimersByTime(SLIDE_MS * 3));
    expect(visible()[0]).toHaveAccessibleName("2 of 3");
    fireEvent.click(screen.getByRole("button", { name: "Play stories" }));
    fireEvent.mouseEnter(container.querySelector('[aria-roledescription="carousel"]')!);
    act(() => vi.advanceTimersByTime(SLIDE_MS * 3));
    expect(visible()[0]).toHaveAccessibleName("2 of 3");
  });
});
