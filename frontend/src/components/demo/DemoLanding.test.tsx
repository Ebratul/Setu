import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { ApiError } from "@/lib/api/client";

const push = vi.fn();
const replace = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  useSearchParams: () => new URLSearchParams(search),
  usePathname: () => "/demo",
}));
vi.mock("@/lib/api/auth", () => ({ demoLogin: vi.fn().mockResolvedValue({}), getMe: vi.fn().mockResolvedValue({}) }));
vi.mock("@/lib/api/demo", async (orig) => {
  const real = await orig<typeof import("@/lib/api/demo")>();
  return { ...real, getPreflight: vi.fn(), startSandbox: vi.fn() };
});
vi.mock("@/components/landing/DemoHub", () => ({ DemoHub: () => <p>playground stops</p> }));
import * as api from "@/lib/api/demo";

import { DemoLanding, runHref } from "./DemoLanding";

const preflight = (ok2 = true) => ({
  ok: ok2,
  replay: true,
  items: [
    { id: "db", label: { en: "Database reachable", bn: "ডেটাবেস" }, ok: true, detail: "ok" },
    { id: "fx", label: { en: "Replay fixtures present", bn: "ফিক্সচার" }, ok: ok2, detail: ok2 ? "7 files" : "missing" },
  ],
});
const renderIt = () => render(<I18nProvider><DemoLanding results={null} /></I18nProvider>);

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  search = "";
  vi.clearAllMocks();
  vi.mocked(api.getPreflight).mockResolvedValue(preflight());
  vi.mocked(api.startSandbox).mockResolvedValue({} as never);
});

describe("DemoLanding", () => {
  it("lists pre-flight results with text and icon, not colour alone", async () => {
    vi.mocked(api.getPreflight).mockResolvedValue(preflight(false));
    renderIt();
    const list = await screen.findByTestId("preflight-list");
    const rows = list.querySelectorAll("li");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-ok", "true");
    expect(rows[1]).toHaveAttribute("data-ok", "false");
    expect(rows[1]).toHaveTextContent("Failed");
    expect(screen.getByTestId("preflight-summary")).toHaveTextContent("needs attention");
  });

  it("refresh re-reads the pre-flight", async () => {
    renderIt();
    await screen.findByTestId("preflight-list");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(api.getPreflight).toHaveBeenCalledTimes(2));
  });

  it("shows a friendly message when the service is unreachable", async () => {
    vi.mocked(api.getPreflight).mockRejectedValue(new TypeError("down"));
    renderIt();
    expect(await screen.findByText(/did not answer/)).toBeInTheDocument();
  });

  it("Watch guided demo creates the sandbox then opens the run with play=1", async () => {
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: /Watch guided demo/ }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/demo/run?play=1"));
    expect(api.startSandbox).toHaveBeenCalled();
  });

  it("Start my own sandbox goes to /app", async () => {
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: "Start my own sandbox" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/app"));
  });

  it("Presenter mode links to the presenter run", () => {
    renderIt();
    expect(screen.getByRole("link", { name: "Presenter mode" })).toHaveAttribute("href", "/demo/run?mode=presenter");
  });

  it("explains a full house (503) instead of failing silently", async () => {
    vi.mocked(api.startSandbox).mockRejectedValue(new ApiError(503, "x", null, "SANDBOX_CAPACITY"));
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: /Watch guided demo/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("busy");
    expect(push).not.toHaveBeenCalled();
  });

  it("keeps the playground stops below and has a single h1", () => {
    renderIt();
    expect(screen.getByText("playground stops")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("redirects /demo?step=9 to the run screen", async () => {
    search = "step=9";
    renderIt();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/demo/run?step=9"));
    expect(api.getPreflight).not.toHaveBeenCalled();
  });
});

describe("runHref", () => {
  it("keeps mode, play and lang and ignores bad steps", () => {
    expect(runHref(new URLSearchParams("step=9&mode=presenter&lang=bn&x=1"))).toBe("/demo/run?step=9&mode=presenter&lang=bn");
    expect(runHref(new URLSearchParams("step=abc"))).toBeNull();
    expect(runHref(new URLSearchParams(""))).toBeNull();
  });
});
