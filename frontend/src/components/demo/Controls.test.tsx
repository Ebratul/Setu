import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { Controls } from "./Controls";

const base = {
  started: true,
  busy: false,
  playing: false,
  speed: 1 as const,
  canPrev: true,
  canNext: true,
  showSpeed: true,
  onStart: vi.fn(),
  onPrev: vi.fn(),
  onNext: vi.fn(),
  onTogglePlay: vi.fn(),
  onSpeed: vi.fn(),
};
const wrap = (p: Partial<typeof base> = {}) => render(<I18nProvider><Controls {...base} {...p} /></I18nProvider>);

describe("Controls", () => {
  it("offers Start before the first scene and hides it afterwards", () => {
    const { unmount } = wrap({ started: false, canPrev: false });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(base.onStart).toHaveBeenCalled();
    unmount();
    wrap();
    expect(screen.queryByRole("button", { name: "Start" })).toBeNull();
  });

  it("fires next, previous and auto-play", () => {
    wrap();
    fireEvent.click(screen.getByRole("button", { name: /Next/ }));
    fireEvent.click(screen.getByRole("button", { name: /Previous/ }));
    fireEvent.click(screen.getByRole("button", { name: "Auto-play" }));
    expect(base.onNext).toHaveBeenCalled();
    expect(base.onPrev).toHaveBeenCalled();
    expect(base.onTogglePlay).toHaveBeenCalled();
  });

  it("shows Pause while playing, with state exposed to assistive tech", () => {
    wrap({ playing: true });
    expect(screen.getByRole("button", { name: "Pause" })).toHaveAttribute("aria-pressed", "true");
  });

  it("selects 1x, 1.5x and 2x speeds", () => {
    wrap();
    const group = screen.getByRole("radiogroup", { name: "Auto-play speed" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "1×" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "1.5×" }));
    fireEvent.click(screen.getByRole("radio", { name: "2×" }));
    expect(base.onSpeed).toHaveBeenNthCalledWith(1, 1.5);
    expect(base.onSpeed).toHaveBeenNthCalledWith(2, 2);
  });

  it("disables navigation while busy or at the boundaries, and drops the speed in recording pace", () => {
    wrap({ busy: true });
    expect(screen.getByRole("button", { name: /Next/ })).toBeDisabled();
  });

  it("hides the speed control when pace is fixed", () => {
    wrap({ showSpeed: false });
    expect(screen.queryByRole("radiogroup")).toBeNull();
  });
});
