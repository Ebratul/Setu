import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SpotlightOverlay } from "./SpotlightOverlay";

const size = { width: 1000, height: 600 };

describe("SpotlightOverlay", () => {
  it("draws a cut-out with the caption bubble and does not intercept pointer events", () => {
    render(<SpotlightOverlay rect={{ left: 100, top: 100, width: 200, height: 50 }} missing={false} size={size} caption="Look here" reducedMotion={false} />);
    const root = screen.getByTestId("spotlight");
    expect(root).toHaveAttribute("data-mode", "cutout");
    expect(root.className).toContain("pointer-events-none");
    expect(screen.getByTestId("spotlight-hole")).toBeInTheDocument();
    expect(screen.getByTestId("spotlight-bubble")).toHaveTextContent("Look here");
  });

  it("falls back to a centred caption when the element is missing", () => {
    render(<SpotlightOverlay rect={null} missing size={size} caption="Centred" reducedMotion={false} />);
    expect(screen.getByTestId("spotlight")).toHaveAttribute("data-mode", "center");
    expect(screen.queryByTestId("spotlight-hole")).toBeNull();
    expect(screen.getByTestId("spotlight-bubble")).toHaveTextContent("Centred");
  });

  it("renders nothing while the element is still being searched for", () => {
    const { container } = render(<SpotlightOverlay rect={null} missing={false} size={size} caption="x" reducedMotion={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("drops the movement transition under reduced motion", () => {
    render(<SpotlightOverlay rect={{ left: 1, top: 1, width: 50, height: 50 }} missing={false} size={size} caption="x" reducedMotion />);
    expect(screen.getByTestId("spotlight-hole").className).not.toContain("transition");
  });
});
