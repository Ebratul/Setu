import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Default to demo auth so API calls in unrelated tests do not trigger a /auth/config fetch.
vi.mock("@/lib/auth/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth/client")>()),
  getAuthMode: () => Promise.resolve("demo" as const),
  getPublicAuthConfig: () =>
    Promise.resolve({
      mode: "demo" as const,
      demoEnabled: true,
      googleEnabled: false,
    }),
}));

afterEach(() => cleanup());
