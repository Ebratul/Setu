import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { SANDBOX, SCRIPT, emptyRun, passed } from "./fixtures";

let search = "mode=presenter";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search),
  usePathname: () => "/demo/run",
}));
vi.mock("next/link", () => ({ default: ({ href, children, ...r }: { href: string; children: React.ReactNode }) => <a href={href} {...r}>{children}</a> }));
vi.mock("@/lib/api/auth", () => ({ demoLogin: vi.fn().mockResolvedValue({}), getMe: vi.fn().mockResolvedValue({ email: "rahima@demo.setu" }) }));
vi.mock("@/lib/api/approvals", () => ({ getDemoPhone: vi.fn().mockResolvedValue([]), PHONE_OPEN: "x" }));
vi.mock("@/lib/api/demo", async (orig) => {
  const real = await orig<typeof import("@/lib/api/demo")>();
  return { ...real, getDemoSteps: vi.fn(), startSandbox: vi.fn(), getRun: vi.fn(), runScene: vi.fn(), gotoStep: vi.fn(), resetRun: vi.fn(), getSummary: vi.fn() };
});
import * as api from "@/lib/api/demo";

import { DemoRunPage } from "./DemoRunPage";

const ROUTES: Record<string, string> = { "1.1": "/app/chat", "2.1": "/app/a", "2.2": "/supplier/d", "3.1": "/app/b" };

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  search = "mode=presenter";
  vi.clearAllMocks();
  vi.mocked(api.getDemoSteps).mockResolvedValue(SCRIPT);
  vi.mocked(api.startSandbox).mockResolvedValue(SANDBOX);
  vi.mocked(api.getRun).mockResolvedValue(emptyRun());
  vi.mocked(api.runScene).mockImplementation(async (n, k) => {
    const r = passed(n, k, ROUTES[`${n}.${k}`]);
    return emptyRun({ scenes: [r], last: r });
  });
});

const renderIt = () => render(<I18nProvider><DemoRunPage /></I18nProvider>);

describe("DemoRunPage", () => {
  it("shows the always-visible banner, one h1, landmarks, and starts on the Start button", async () => {
    renderIt();
    expect(await screen.findByTestId("sim-banner")).toHaveTextContent("Simulated sandbox – fictional data");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Start" })[0]).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Start" })[0]);
    await waitFor(() => expect(api.runScene).toHaveBeenCalledWith(1, 1));
    expect(await screen.findByTestId("progress")).toHaveTextContent("Step 1 · 1/1");
    const frame = await screen.findByTitle("Setu app screen for the current demo scene");
    expect(frame).toHaveAttribute("src", "/app/chat?embed=1");
  });

  it("presenter keys: ArrowRight goes next, but not while typing in a field", async () => {
    renderIt();
    await screen.findByTestId("sim-banner");
    fireEvent.click(screen.getAllByRole("button", { name: "Start" })[0]);
    await waitFor(() => expect(api.runScene).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("progress")).toBeInTheDocument());
    await waitFor(() => expect(screen.queryByTestId("stage-busy")).toBeNull());
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    fireEvent.keyDown(input, { key: "ArrowRight" });
    expect(api.runScene).toHaveBeenCalledTimes(1);
    input.remove();
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    await waitFor(() => expect(api.runScene).toHaveBeenCalledTimes(2));
  });

  it("N toggles the notes pane, B toggles blackout, R asks for confirmation", async () => {
    renderIt();
    await screen.findByTestId("sim-banner");
    fireEvent.click(screen.getAllByRole("button", { name: "Start" })[0]);
    await waitFor(() => expect(screen.getByTestId("progress")).toBeInTheDocument());
    fireEvent.keyDown(document.body, { key: "n" });
    expect(await screen.findByTestId("notes")).toHaveTextContent("Open with the person.");
    fireEvent.keyDown(document.body, { key: "n" });
    expect(screen.queryByTestId("notes")).toBeNull();
    fireEvent.keyDown(document.body, { key: "b" });
    expect(screen.getByRole("button", { name: /blacked out/ })).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: "b" });
    expect(screen.queryByRole("button", { name: /blacked out/ })).toBeNull();
    fireEvent.keyDown(document.body, { key: "r" });
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(api.resetRun).not.toHaveBeenCalled();
  });

  it("normal mode ignores presenter shortcuts", async () => {
    search = "";
    renderIt();
    await screen.findByTestId("sim-banner");
    fireEvent.keyDown(document.body, { key: "r" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("recording mode renders a clean 1920x1080 stage with no side panels or speed controls", async () => {
    search = "mode=record";
    renderIt();
    const stage = await screen.findByTestId("record-stage");
    expect(stage.style.width).toBe("1920px");
    expect(stage.style.height).toBe("1080px");
    expect(screen.getByTestId("record-root").className).toContain("cursor-none");
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.queryByTestId("scorecard")).toBeNull();
    await waitFor(() => expect(api.runScene).toHaveBeenCalledWith(1, 1));
    expect(await screen.findByText("Ask in Bangla")).toBeInTheDocument();
  });

  it("offers a new sandbox when the old one has expired", async () => {
    const { ApiError } = await import("@/lib/api/client");
    search = "";
    renderIt();
    await screen.findByTestId("sim-banner");
    vi.mocked(api.runScene).mockRejectedValueOnce(new ApiError(410, "x", null, "SANDBOX_EXPIRED"));
    fireEvent.click(screen.getAllByRole("button", { name: "Start" })[0]);
    expect(await screen.findByRole("button", { name: "Start a new sandbox" })).toBeInTheDocument();
    expect(screen.getByText(/has expired/)).toBeInTheDocument();
  });

  it("uses the three mobile tabs", async () => {
    search = "";
    renderIt();
    await screen.findByTestId("sim-banner");
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["App", "Story", "Score"]);
    fireEvent.click(screen.getByRole("tab", { name: "Score" }));
    expect(screen.getByRole("tab", { name: "Score" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("mobile-controls")).toBeInTheDocument();
  });
});
