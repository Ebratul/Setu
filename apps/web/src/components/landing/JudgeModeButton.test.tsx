import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const demoLogin = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
const startSandbox = vi.fn();
vi.mock("@/lib/api/auth", () => ({ demoLogin: (e: string) => demoLogin(e) }));
vi.mock("@/lib/api/demo", () => ({ startSandbox: () => startSandbox() }));

import { JudgeModeButton } from "./JudgeModeButton";

describe("JudgeModeButton", () => {
  beforeEach(() => {
    push.mockReset();
    demoLogin.mockReset();
  });

  it("logs in as the judge and opens /demo?judge=1", async () => {
    demoLogin.mockResolvedValue({});
    render(<JudgeModeButton />);
    fireEvent.click(screen.getByRole("button", { name: "Judge mode" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/demo?judge=1"));
    expect(demoLogin).toHaveBeenCalledWith("judge@demo.setu");
  });

  it("creates the sandbox first when withSandbox is set", async () => {
    demoLogin.mockResolvedValue({});
    startSandbox.mockResolvedValue({});
    render(<JudgeModeButton withSandbox label="Create my sandbox" />);
    fireEvent.click(screen.getByRole("button", { name: "Create my sandbox" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/demo?judge=1"));
    expect(startSandbox).toHaveBeenCalledTimes(1);
  });

  it("shows an alert with retry when login fails", async () => {
    demoLogin.mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce({});
    render(<JudgeModeButton />);
    fireEvent.click(screen.getByRole("button", { name: "Judge mode" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not start Judge mode/);
    expect(push).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/demo?judge=1"));
  });
});
