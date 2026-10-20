import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { messages } from "@/i18n";

import { ErrorPageView } from "./ErrorPageView";
import { NotFoundView } from "./NotFoundView";
import { renderI18n, setLang } from "./testUtils";

vi.mock("next/navigation", () => ({ usePathname: () => "/nope" }));

describe("404 and 500 pages", () => {
  it("renders the 404 page in Bangla with one h1 and a way home", () => {
    setLang("bn");
    renderI18n(<NotFoundView />);
    expect(screen.getByRole("heading", { level: 1, name: messages.bn["notfound.title"] })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: messages.bn["notfound.home"] })).toHaveAttribute("href", "/app");
  });

  it("renders the 404 page in Chinese", () => {
    setLang("zh");
    renderI18n(<NotFoundView />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(messages.zh["notfound.title"]);
  });

  it("renders the 500 page with a retry and the digest", () => {
    setLang("en");
    const reset = vi.fn();
    renderI18n(<ErrorPageView error={Object.assign(new Error("x"), { digest: "abc123" })} reset={reset} />);
    screen.getByRole("button", { name: "Try again" }).click();
    expect(reset).toHaveBeenCalled();
    expect(screen.getByText("Reference: abc123")).toBeInTheDocument();
  });
});
