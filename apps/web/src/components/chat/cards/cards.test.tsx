import { render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";

import alerts from "../fixtures/alerts.json";
import cashflow from "../fixtures/cashflow.json";
import financing from "../fixtures/financing.json";
import fxCompare from "../fixtures/fxCompare.json";
import kyb from "../fixtures/kyb.json";
import landedCost from "../fixtures/landedCost.json";
import monthly from "../fixtures/monthlySummary.json";
import scorecard from "../fixtures/scorecard.json";
import { ChatCard } from "./ChatCard";

beforeAll(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

function show(card: unknown) {
  return render(
    <I18nProvider>
      <ChatCard card={card as ChatCardData} />
    </I18nProvider>,
  );
}

describe("FinancingComparisonCard", () => {
  it("highlights the recommended option, greys out ineligible ones and links Apply", () => {
    show(financing);
    const options = screen.getAllByTestId("chat-option");
    expect(options.length).toBeGreaterThanOrEqual(3);
    const rec = options.find((o) => o.dataset.recommended === "true")!;
    expect(rec.dataset.code).toBe("supplier-credit-huaxin");
    expect(within(rec).getByText("$31.20")).toBeInTheDocument();
    expect(within(rec).getByText("Recommended")).toBeInTheDocument();
    expect(within(rec).getByText(/No collateral needed/)).toBeInTheDocument();
    const apply = within(rec).getByRole("link", { name: /apply/i });
    expect(apply).toHaveAttribute(
      "href",
      "/app/financing?deal=SETU-2026-0001&mode=shortfall",
    );
    const ineligible = options.find((o) => o.dataset.eligible === "false")!;
    expect(within(ineligible).getByText(/Minimum amount USD 3,000.00/)).toBeInTheDocument();
    expect(within(ineligible).queryByRole("link")).toBeNull();
    expect(screen.getAllByText("Simulated data").length).toBeGreaterThan(0);
  });

  it("hides Apply when apply_route is not a financing route", () => {
    show({
      ...financing,
      data: { ...financing.data, apply_route: "/app/approvals" },
    });
    expect(screen.queryByRole("link", { name: /apply/i })).toBeNull();
  });

  it("shows the Bangla explanation when the UI language is Bangla", () => {
    document.cookie = "setu_lang=bn; path=/";
    show(financing);
    expect(
      screen.getByText(/প্রস্তাবিত: Supplier credit — Shaoxing Huaxin/),
    ).toBeInTheDocument();
  });
});

describe("CashflowCard", () => {
  it("shows the first shortfall amount and date", () => {
    show(cashflow);
    expect(screen.getAllByText("$1,560.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Nov 7, 2026").length).toBeGreaterThan(0);
    const link = screen.getByRole("link", { name: /open cash flow/i });
    expect(link).toHaveAttribute("href", "/app/cashflow");
    expect(screen.getByText(/Staff salaries/)).toBeInTheDocument();
    expect(screen.getByTestId("cashflow-legend")).not.toHaveTextContent(
      "After scenario",
    );
  });

  it("adds a before/after legend when the scenario side exists", () => {
    show({
      ...cashflow,
      data: {
        ...cashflow.data,
        after: {
          ...cashflow.data.before,
          first_shortfall: null,
          lowest_balance: "1200.00",
        },
        scenario_label: "Delay milestone 2 by 14 days",
      },
    });
    const legend = screen.getByTestId("cashflow-legend");
    expect(legend).toHaveTextContent("Before");
    expect(legend).toHaveTextContent("After scenario");
    expect(screen.getByText(/Delay milestone 2/)).toBeInTheDocument();
  });
});

describe("other cards", () => {
  it("LandedCostCard shows KPIs and an analysis link", () => {
    show(landedCost);
    expect(screen.getAllByText("$11,200.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/18\.01%/).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /open analysis/i })).toHaveAttribute(
      "href",
      "/app/orders/SETU-2026-0001/analysis",
    );
  });

  it("FxCompareCard highlights the cheaper route and lists assumptions", () => {
    const { container } = show(fxCompare);
    expect(container.querySelector('[data-route="CNY"]')).toHaveAttribute(
      "data-cheaper",
      "true",
    );
    expect(container.querySelector('[data-route="USD"]')).toHaveAttribute(
      "data-cheaper",
      "false",
    );
    expect(screen.getByText(/MOCK/)).toBeInTheDocument();
    expect(screen.getByText(/Bank sells USD at mid/)).toBeInTheDocument();
  });

  it("AlertsCard sorts by severity and only links internal routes", () => {
    const evil = structuredClone(alerts);
    evil.data.alerts[0].route = "https://evil.example";
    const { container } = show(evil);
    expect(container.querySelectorAll("a").length).toBe(
      evil.data.alerts.filter((a) => a.route?.startsWith("/app")).length,
    );
    const first = container.querySelector("li[data-alert-type]")!;
    expect(first.textContent).toMatch(/Warning/);
  });

  it("MonthlySummaryCard and ScorecardCard render; weak suppliers are flagged", () => {
    show(monthly);
    expect(screen.getAllByText("$11,200.00").length).toBeGreaterThan(0);
    show(scorecard);
    const weakRow = screen
      .getByText("Guangzhou Huameng Trading Co., Ltd.")
      .closest("tr")!;
    expect(weakRow).toHaveAttribute("data-weak", "true");
    expect(within(weakRow).getByText("Weak supplier")).toBeInTheDocument();
  });
});

describe("no approval controls", () => {
  it("never renders an approve or release control in any card", () => {
    for (const c of [alerts, cashflow, financing, fxCompare, landedCost, monthly, scorecard]) {
      const { unmount } = show(c);
      const controls = [
        ...screen.queryAllByRole("button"),
        ...screen.queryAllByRole("link"),
      ];
      for (const el of controls) {
        expect(el.textContent).not.toMatch(/approve|release|confirm|otp/i);
      }
      unmount();
    }
  });
});

describe("KybCard", () => {
  it("shows the status badge, top reasons and a safe supplier link", () => {
    show(kyb);
    expect(screen.getByTestId("kyb-badge")).toHaveAttribute("data-status", "WARNING");
    expect(screen.getByText("Personal account for a company.")).toBeInTheDocument();
    expect(screen.getByText("4 of 7 checks passed")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Open supplier profile/ }),
    ).toHaveAttribute("href", kyb.data.supplier_route);
  });

  it("drops a link that is not an internal /app route", () => {
    show({ ...kyb, data: { ...kyb.data, supplier_route: "https://evil.example/x" } });
    expect(screen.queryByRole("link")).toBeNull();
  });
});
