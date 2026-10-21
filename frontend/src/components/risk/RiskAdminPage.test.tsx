import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { risk } from "./fixtures";
import { RiskAdminPage } from "./RiskAdminPage";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const reply = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

const event = {
  id: "e1",
  ts: "2026-10-18T10:00:00Z",
  deal_ref: "SETU-2026-0001",
  action: "RELEASE_TRANCHE",
  origin: "USER_UI",
  decision: "BLOCK",
  tier: 3,
  reason_codes: ["AMOUNT_OVER_LIMIT"],
  explanation_en: "",
  explanation_bn: "",
  trace: risk().trace,
  hints: [],
};

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      url.endsWith("/risk/policy")
        ? reply({ source: "config/risk.yaml", yaml: "tier1_max_usd: 20000", tier1_max_usd: "20000", fraud_score_tier3_above: 60, new_beneficiary_days: 30, cooling_off_minutes: 10, rules: [] })
        : reply({
            simulated: true,
            counters: { auto_released: 5, one_tap: 3, otp_required: 2, blocked: 1 },
            series: [{ day: "2026-10-18", auto: 5, one_tap: 3, otp: 2, blocked: 1 }],
            latest_blocked: [event],
            recent: [event],
          }),
    ),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("RiskAdminPage", () => {
  it("renders counters, chart table fallback and expandable trace", async () => {
    render(
      <I18nProvider>
        <RiskAdminPage />
      </I18nProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("counter-blocked")).toHaveTextContent("1"));
    expect(screen.getByTestId("counter-auto")).toHaveTextContent("5");
    fireEvent.click(screen.getByRole("button", { name: "Show chart data as a table" }));
    expect(screen.getByTestId("risk-series-table")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show rule trace" }));
    expect(screen.getByTestId("rule-trace")).toBeInTheDocument();
    await screen.findByTestId("policy-table");
  });

  it("shows no-access on 403", async () => {
    vi.stubGlobal("fetch", vi.fn(() => reply({ detail: "no" }, 403)));
    render(
      <I18nProvider>
        <RiskAdminPage />
      </I18nProvider>,
    );
    expect((await screen.findAllByText("You do not have access to this page")).length).toBeGreaterThan(0);
  });
});
