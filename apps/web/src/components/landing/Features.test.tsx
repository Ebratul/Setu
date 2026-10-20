import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Features } from "./Features";

describe("Features", () => {
  it("links each card's See it to /demo?step=N in order", () => {
    render(<Features />);
    const links = screen.getAllByRole("link", { name: /^See it:/ });
    expect(links).toHaveLength(7);
    links.forEach((a, i) => expect(a).toHaveAttribute("href", `/demo?step=${i + 1}`));
    expect(links[0]).toHaveAccessibleName("See it: Financing matching");
    expect(links[6]).toHaveAccessibleName("See it: Bangla/Chinese chat");
  });
});
