import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang } from "@/components/shell/testUtils";

import { ChatSheet, CHAT_WIDTH_KEY, clampWidth, MIN_W } from "./ChatSheet";

beforeEach(() => {
  localStorage.clear();
  setLang("en");
});

describe("ChatSheet", () => {
  it("is a labelled dialog that closes on Escape", () => {
    const onClose = vi.fn();
    renderI18n(
      <ChatSheet title="Ask Setu" onClose={onClose}>
        <button>inside</button>
      </ChatSheet>,
    );
    expect(screen.getByRole("dialog", { name: "Ask Setu" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("resizes with the arrow keys, clamps, and remembers the width", async () => {
    renderI18n(
      <ChatSheet title="Ask Setu" onClose={vi.fn()}>
        <p>x</p>
      </ChatSheet>,
    );
    const handle = screen.getByRole("separator", { name: "Resize chat panel" });
    const before = Number(handle.getAttribute("aria-valuenow"));
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(Number(handle.getAttribute("aria-valuenow"))).toBeGreaterThan(before);
    expect(localStorage.getItem(CHAT_WIDTH_KEY)).not.toBeNull();
    fireEvent.keyDown(handle, { key: "Home" });
    expect(handle).toHaveAttribute("aria-valuenow", String(MIN_W));
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(handle).toHaveAttribute("aria-valuenow", String(MIN_W));
  });

  it("restores a saved width", async () => {
    localStorage.setItem(CHAT_WIDTH_KEY, "600");
    renderI18n(
      <ChatSheet title="Ask Setu" onClose={vi.fn()}>
        <p>x</p>
      </ChatSheet>,
    );
    await waitFor(() =>
      expect(screen.getByRole("separator")).toHaveAttribute("aria-valuenow", String(clampWidth(600, window.innerWidth))),
    );
  });
});
