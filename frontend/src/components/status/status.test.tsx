import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getHealth = vi.fn();
vi.mock("@/lib/api/client", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/api/client")>(
      "@/lib/api/client",
    );
  return { ...actual, getHealth: (s?: AbortSignal) => getHealth(s) };
});

import { healthLevel, parseHealth } from "@/lib/health";

import { FooterStatus } from "./FooterStatus";

describe("health parsing", () => {
  it("accepts the old payload with no new fields", () => {
    const h = parseHealth({ status: "ok", db: "ok", version: "0.1.0" });
    expect(h.gitSha).toBeNull();
    expect(h.ready).toBeNull();
    expect(healthLevel(h)).toBe("ok");
  });
  it("is degraded when any reported check fails", () => {
    expect(healthLevel(parseHealth({ status: "ok", db: "unavailable" }))).toBe(
      "degraded",
    );
    expect(healthLevel(parseHealth({ status: "degraded" }))).toBe("degraded");
    expect(healthLevel(parseHealth({ status: "ok", kb_indexed: false }))).toBe(
      "degraded",
    );
  });
  it("survives garbage", () => {
    expect(healthLevel(parseHealth("nope"))).toBe("ok");
  });
});

describe("FooterStatus", () => {
  beforeEach(() => {
    getHealth.mockClear();
  });
  afterEach(() => vi.unstubAllEnvs());

  it("shows OK with text and the agent version", async () => {
    getHealth.mockResolvedValue({
      status: "ok",
      db: "ok",
      version: "1.2.3",
      git_sha: "abcdef123456",
      built_at: "2026-10-20T10:00:00Z",
      kb_indexed: true,
      audit_key_loaded: true,
      replay_fixtures_present: true,
    });
    render(<FooterStatus />);
    await waitFor(() =>
      expect(screen.getByTestId("system-status")).toHaveAttribute(
        "data-level",
        "ok",
      ),
    );
    expect(screen.getByTestId("system-status")).toHaveTextContent("OK");
    expect(screen.getByTestId("version-agent")).toHaveTextContent(
      "v1.2.3 · abcdef1 · 2026-10-20 10:00 UTC",
    );
    expect(screen.getByRole("link", { name: /System/ })).toHaveAttribute(
      "href",
      "/judges#status",
    );
  });

  it("shows degraded when the database is unavailable", async () => {
    getHealth.mockResolvedValue({
      status: "ok",
      db: "unavailable",
      version: "0.1.0",
    });
    render(<FooterStatus />);
    await waitFor(() =>
      expect(screen.getByTestId("system-status")).toHaveAttribute(
        "data-level",
        "degraded",
      ),
    );
    expect(screen.getByTestId("system-status")).toHaveTextContent("Degraded");
  });

  it("shows unreachable (text, not colour only) when the request fails", async () => {
    getHealth.mockImplementation(() =>
      Promise.reject(new TypeError("fetch failed")),
    );
    render(<FooterStatus />);
    await waitFor(() =>
      expect(screen.getByTestId("system-status")).toHaveAttribute(
        "data-level",
        "unreachable",
      ),
    );
    expect(screen.getByTestId("system-status")).toHaveTextContent(
      "Unreachable",
    );
    expect(screen.getByTestId("version-agent")).toHaveTextContent(
      "unavailable",
    );
  });

  it("version badge falls back to dev for the web build", async () => {
    getHealth.mockResolvedValue({ status: "ok", db: "ok", version: "0.1.0" });
    render(<FooterStatus />);
    expect(screen.getByTestId("version-web")).toHaveTextContent("dev");
    await waitFor(() =>
      expect(screen.getByTestId("version-agent")).toHaveTextContent("v0.1.0"),
    );
  });

  it("does not poll while the tab is hidden and polls every 60 s when visible", async () => {
    vi.useFakeTimers();
    getHealth.mockResolvedValue({ status: "ok", db: "ok", version: "0.1.0" });
    render(<FooterStatus />);
    await act(async () => {});
    expect(getHealth).toHaveBeenCalledTimes(1);
    const vis = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("hidden");
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(getHealth).toHaveBeenCalledTimes(1);
    vis.mockReturnValue("visible");
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(getHealth).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
});
