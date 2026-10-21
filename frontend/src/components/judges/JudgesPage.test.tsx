import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api/auth", () => ({ demoLogin: vi.fn() }));
vi.mock("@/lib/api/demo", () => ({ startSandbox: vi.fn() }));
vi.mock("@/lib/api/client", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/api/client")>(
      "@/lib/api/client",
    );
  return { ...actual, getHealth: () => new Promise(() => {}) };
});

import { JudgesPage } from "./JudgesPage";
import { SCORE_ROWS, safeUrl } from "./links";

describe("JudgesPage", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("renders the hero actions, tour order, scorecard and QR codes", async () => {
    render(<JudgesPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Judge quick-start",
    );
    expect(
      screen.getByRole("link", { name: "Open the live demo" }),
    ).toHaveAttribute("href", "/demo");
    expect(
      screen.getByRole("button", { name: "Create my sandbox" }),
    ).toBeInTheDocument();
    const tour = within(
      screen.getByRole("heading", { name: /60 seconds/ }).closest("section")!,
    ).getAllByRole("listitem");
    expect(tour).toHaveLength(5);
    expect(tour[1]).toHaveTextContent("Risk Playground");
    expect(screen.getAllByTestId("score-row")).toHaveLength(SCORE_ROWS.length);
    expect(await screen.findByTestId("qr-demo")).toContainHTML("<svg");
    expect(screen.getByTestId("qr-judges")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("/judges"),
    );
    expect(
      screen.getByRole("button", {
        name: /Download PNG of the QR code for Live demo/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("status-panel")).toBeInTheDocument();
  });

  it("marks unset links as coming and never renders a dead href", () => {
    render(<JudgesPage />);
    for (const id of ["docs", "repo", "video"]) {
      const li = screen.getByTestId(`resource-${id}`);
      expect(li).toHaveTextContent("Link coming");
      expect(li.querySelector("a")).toBeNull();
    }
    expect(
      screen.getByTestId("resource-status").querySelector("a"),
    ).toHaveAttribute("href", "#status");
  });

  it("uses env links and credentials when set", () => {
    vi.stubEnv("NEXT_PUBLIC_REPO_URL", "https://example.com/org/setu");
    vi.stubEnv("NEXT_PUBLIC_VIDEO_URL", "https://example.com/v");
    vi.stubEnv("NEXT_PUBLIC_JUDGE_EMAIL", "j@x.test");
    vi.stubEnv("NEXT_PUBLIC_JUDGE_NOTE", "Use the Demo Judge card");
    render(<JudgesPage />);
    expect(
      screen.getByTestId("resource-repo").querySelector("a"),
    ).toHaveAttribute("href", "https://example.com/org/setu");
    expect(
      screen.getByTestId("resource-docs").querySelector("a"),
    ).toHaveAttribute("href", "https://example.com/org/setu/tree/main/docs");
    expect(screen.getByTestId("judge-email")).toHaveTextContent("j@x.test");
    expect(screen.getByTestId("judge-note")).toHaveTextContent(
      "Use the Demo Judge card",
    );
  });

  it("rejects non-http urls", () => {
    expect(safeUrl("javascript:alert(1)")).toBeNull();
    expect(safeUrl("not a url")).toBeNull();
    expect(safeUrl("https://a.test/x")).toBe("https://a.test/x");
  });
});
