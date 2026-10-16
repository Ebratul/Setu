import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentStatusCard } from "./AgentStatusCard";

afterEach(() => vi.unstubAllGlobals());

describe("AgentStatusCard", () => {
  it("shows agent online and DB ok when /health succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: "ok",
            service: "setu-agent",
            db: "ok",
            version: "0.1.0",
          }),
          { status: 200 },
        ),
      ),
    );
    render(<AgentStatusCard />);
    expect(await screen.findByText("online")).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/health");
  });

  it("shows agent offline and DB unavailable when the agent is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("fetch failed")),
    );
    render(<AgentStatusCard />);
    expect(await screen.findByText("offline")).toBeInTheDocument();
    expect(screen.getByText("unavailable")).toBeInTheDocument();
  });
});
