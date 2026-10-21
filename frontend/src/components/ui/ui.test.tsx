import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";

import { Alert } from "./Alert";
import { Amount } from "./Amount";
import { Badge } from "./Badge";
import { CountUp } from "./CountUp";
import { DataTable } from "./DataTable";
import { Drawer } from "./Drawer";
import { StatusChip } from "./StatusChip";
import { TierBadge } from "./TierBadge";

function wrap(node: React.ReactNode) {
  return render(<I18nProvider>{node}</I18nProvider>);
}

describe("Badge", () => {
  it.each(["neutral", "success", "warning", "danger", "info"] as const)(
    "%s always renders an icon next to its text",
    (tone) => {
      const { container } = wrap(<Badge tone={tone}>label</Badge>);
      expect(container.querySelector("svg")).not.toBeNull();
      expect(screen.getByText("label")).toBeInTheDocument();
    },
  );
});

describe("Amount", () => {
  it("formats server decimals with symbol and names the currency for screen readers", () => {
    wrap(<Amount value="12500.50" currency="USD" />);
    const el = screen.getByLabelText(/US dollar/);
    expect(el).toHaveAttribute("title", "USD");
    expect(el.textContent).toBe("$12,500.50");
  });

  it("keeps full precision (no float rounding) and handles negatives and each symbol", () => {
    wrap(
      <>
        <Amount value="-0.1234" currency="BDT" />
        <Amount value="90071992547409.93" currency="CNY" />
      </>,
    );
    expect(screen.getByLabelText(/taka/).textContent).toBe("-৳0.1234");
    expect(screen.getByLabelText(/yuan/).textContent).toBe("¥90,071,992,547,409.93");
  });
});

describe("TierBadge", () => {
  it.each([
    [0, "neutral", /tier 0/i],
    [1, "info", /tier 1/i],
    [2, "warning", /tier 2/i],
    [3, "danger", /tier 3/i],
  ])("tier %i maps to %s with icon and text", (tier, tone, text) => {
    const { container } = wrap(<TierBadge tier={tier} />);
    expect(container.querySelector(`[data-tone="${tone}"]`)).not.toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.textContent).toMatch(text);
  });

  it("BLOCK decision overrides the tier", () => {
    const { container } = wrap(<TierBadge tier={1} decision="BLOCK" />);
    expect(container.querySelector('[data-tier="blocked"]')).not.toBeNull();
  });
});

describe("StatusChip", () => {
  it("maps known codes to a tone and unknown codes to neutral", () => {
    const { container } = wrap(
      <>
        <StatusChip status="FAILED" />
        <StatusChip status="whatever_new" />
      </>,
    );
    expect(container.querySelector('[data-tone="danger"]')).not.toBeNull();
    expect(container.querySelector('[data-tone="neutral"]')).not.toBeNull();
    expect(screen.getByText("whatever new")).toBeInTheDocument();
  });
});

describe("Alert", () => {
  it("urgent alerts use role=alert, others a polite status", () => {
    wrap(
      <>
        <Alert urgent title="Frozen" />
        <Alert title="FYI" />
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Frozen");
    expect(screen.getByRole("status")).toHaveTextContent("FYI");
  });
});

describe("CountUp", () => {
  it("settles on the exact server value", async () => {
    wrap(<CountUp value="1234.50" durationMs={0} />);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });
    expect(screen.getByText("1,234.50")).toBeInTheDocument();
  });
});

describe("DataTable", () => {
  const rows = [
    { id: "a", name: "Zeta", qty: 2 },
    { id: "b", name: "Alpha", qty: 10 },
  ];
  it("sorts when a sortable header is activated and exposes aria-sort", () => {
    wrap(
      <DataTable
        caption="Items"
        rows={rows}
        rowKey={(r) => r.id}
        columns={[
          { id: "name", header: "Name", cell: (r) => r.name, sortValue: (r) => r.name },
          { id: "qty", header: "Qty", cell: (r) => r.qty },
        ]}
      />,
    );
    const table = screen.getByRole("table", { hidden: true });
    const firstCell = () => table.querySelectorAll("tbody tr")[0].textContent;
    expect(firstCell()).toContain("Zeta");
    fireEvent.click(screen.getByRole("button", { name: /Name/, hidden: true }));
    expect(firstCell()).toContain("Alpha");
    expect(table.querySelector("th")).toHaveAttribute("aria-sort", "ascending");
  });
});

describe("Drawer", () => {
  it("is a labelled modal dialog that closes on Escape", () => {
    let closed = false;
    wrap(
      <Drawer title="Details" onClose={() => (closed = true)}>
        body
      </Drawer>,
    );
    expect(screen.getByRole("dialog", { name: "Details" })).toHaveAttribute("aria-modal", "true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(closed).toBe(true);
  });
});
