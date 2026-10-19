import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

import { PrivacyCounter } from "./PrivacyCounter";

const reply = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});
afterEach(() => vi.unstubAllGlobals());

describe("PrivacyCounter", () => {
  it("shows protected and leaked counts and passes the thread id", async () => {
    const fetchMock = vi.fn(() => reply({ protected: 7, leaked: 0, calls: 3, by_type: {} }));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <I18nProvider>
        <PrivacyCounter threadId="t-1" />
      </I18nProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("privacy-counter")).toHaveTextContent(
        /Identifiers protected this session: 7.*Leaked: 0/,
      ),
    );
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toContain("/privacy/summary?thread_id=t-1");
    expect(screen.getByTestId("privacy-counter-leaked")).toHaveClass("text-success");
  });

  it("renders leaks in the danger colour with an icon", async () => {
    vi.stubGlobal("fetch", vi.fn(() => reply({ protected: 2, leaked: 1, calls: 1, by_type: {} })));
    render(
      <I18nProvider>
        <PrivacyCounter />
      </I18nProvider>,
    );
    const leaked = await screen.findByTestId("privacy-counter-leaked");
    expect(leaked).toHaveClass("text-danger");
    expect(leaked).toHaveTextContent("⚠ Leaked: 1");
  });

  it("refetches when refreshKey changes and polls every 15 s", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.fn(() => reply({ protected: 1, leaked: 0, calls: 1, by_type: {} }));
    vi.stubGlobal("fetch", fetchMock);
    const ui = (k: string) => (
      <I18nProvider>
        <PrivacyCounter refreshKey={k} />
      </I18nProvider>
    );
    const { rerender } = render(ui("a"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    rerender(ui("b"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await vi.advanceTimersByTimeAsync(15_100);
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3));
    vi.useRealTimers();
  });
});
