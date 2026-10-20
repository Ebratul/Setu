import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { risk } from "./fixtures";
import { RiskPlayground } from "./RiskPlayground";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const fetchMock = vi.fn();

function reply(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  fetchMock.mockReset();
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/risk/policy")) return reply({ tier1_max_usd: "20000" });
    const facts = JSON.parse(String(init?.body));
    if (facts.sanctions_hit) {
      return reply({
        ...risk({ decision: "BLOCK", tier: 3, reasons: ["SANCTIONS"], trace: [], hints: [] }),
        dry_run: true,
        saved: false,
      });
    }
    return reply({
      ...risk({ decision: "ALLOW", tier: 1, reasons: [], decided_by: [] }),
      dry_run: true,
      saved: false,
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("RiskPlayground", () => {
  it("shows the dry-run and Simulated notes and updates the tier badge after the debounce", async () => {
    render(
      <I18nProvider>
        <RiskPlayground />
      </I18nProvider>,
    );
    expect(screen.getByText("Dry run — nothing is saved")).toBeInTheDocument();
    expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByTestId("tier-badge")).toHaveAttribute("data-tier", "1"));

    fireEvent.click(screen.getByLabelText("Sanctions hit"));
    await waitFor(() => expect(screen.getByTestId("tier-badge")).toHaveAttribute("data-tier", "blocked"), {
      timeout: 2000,
    });
    expect(screen.getByTestId("risk-decision")).toHaveTextContent("Blocked");
    const evalCalls = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/risk/evaluate"));
    const last = JSON.parse(String(evalCalls.at(-1)?.[1].body));
    expect(last).toMatchObject({ sanctions_hit: true, amount_usd: "9600" });
  });

  it("keeps the slider and numeric amount in sync", async () => {
    render(
      <I18nProvider>
        <RiskPlayground />
      </I18nProvider>,
    );
    fireEvent.change(screen.getByLabelText("Amount in USD (number)"), { target: { value: "22000" } });
    expect(screen.getByLabelText("Amount (USD)")).toHaveValue("22000");
  });
});
