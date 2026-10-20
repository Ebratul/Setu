import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "@/lib/api/auth";
import { listDeals } from "@/lib/api/deals";
import { getSuppliers } from "@/lib/api/kyb";

import CommandPalette from "./CommandPalette";
import { renderI18n, setLang, user } from "./testUtils";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/app",
}));
vi.mock("@/lib/api/auth", () => ({ getMe: vi.fn() }));
vi.mock("@/lib/api/deals", () => ({ listDeals: vi.fn() }));
vi.mock("@/lib/api/kyb", () => ({ getSuppliers: vi.fn() }));

beforeEach(() => {
  push.mockReset();
  setLang("en");
  vi.mocked(getMe).mockResolvedValue(user("ADMIN"));
  vi.mocked(listDeals).mockResolvedValue({
    deals: [{ id: "d1", reference: "SETU-2026-0001", title: "LED panels", supplier_name: "Shenzhen Bright" }],
  } as never);
  vi.mocked(getSuppliers).mockResolvedValue({
    suppliers: [{ supplier_id: "s1", name: "Hangzhou Textiles", city: "Hangzhou" }],
  } as never);
});

describe("CommandPalette", () => {
  it("is an accessible combobox that filters and navigates on Enter", async () => {
    const onClose = vi.fn();
    renderI18n(<CommandPalette onClose={onClose} />);
    const box = screen.getByRole("combobox", { name: "Search" });
    await waitFor(() => expect(box).toHaveFocus());
    fireEvent.change(box, { target: { value: "cash" } });
    const opt = await screen.findByRole("option", { name: /Cash Flow/ });
    expect(box).toHaveAttribute("aria-activedescendant", opt.id);
    fireEvent.keyDown(box, { key: "Enter" });
    expect(push).toHaveBeenCalledWith("/app/cashflow");
    expect(onClose).toHaveBeenCalled();
  });

  it("finds deals and suppliers loaded lazily and moves with the arrow keys", async () => {
    renderI18n(<CommandPalette onClose={vi.fn()} />);
    const box = screen.getByRole("combobox");
    fireEvent.change(box, { target: { value: "hangzhou" } });
    await screen.findByRole("option", { name: /Hangzhou Textiles/ });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(push).toHaveBeenCalledWith("/app/suppliers/s1");

    push.mockReset();
    fireEvent.change(box, { target: { value: "SETU-2026" } });
    await screen.findByRole("option", { name: /SETU-2026-0001/ });
    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "ArrowUp" });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(push).toHaveBeenCalledWith("/app/deals/SETU-2026-0001");
  });

  it("offers quick actions, survives API errors and reports empty results", async () => {
    vi.mocked(listDeals).mockRejectedValue(new Error("down"));
    vi.mocked(getSuppliers).mockRejectedValue(new Error("down"));
    renderI18n(<CommandPalette onClose={vi.fn()} />);
    const box = screen.getByRole("combobox");
    fireEvent.change(box, { target: { value: "new order" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(push).toHaveBeenCalledWith("/app/deals/new");
    fireEvent.change(box, { target: { value: "zzzzqq" } });
    expect((await screen.findAllByText(/No matches/)).length).toBeGreaterThan(0);
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    renderI18n(<CommandPalette onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
