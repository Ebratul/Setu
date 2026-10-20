import { describe, expect, it } from "vitest";

import { sanitizeCitations } from "./chat";

const base = {
  cite_id: "S1",
  source_id: "ug-en-buyer-approvals",
  title: "Approvals",
  heading_path: "How to",
  source_type: "user_guide",
  original_reference: "/docs/en/buyer/approvals",
  last_reviewed: "2026-10-20",
  disclaimer: "",
};

describe("sanitizeCitations guide_url", () => {
  it("keeps same-site doc links", () => {
    expect(sanitizeCitations([{ ...base, guide_url: "/docs/en/buyer/approvals#how-to" }])[0].guide_url).toBe(
      "/docs/en/buyer/approvals#how-to",
    );
  });
  it("drops anything else", () => {
    for (const bad of ["https://evil.example/docs/en/a/b", "//evil.example", "javascript:alert(1)", "/docs/en/../../x", "/app/approvals"]) {
      expect(sanitizeCitations([{ ...base, guide_url: bad }])[0].guide_url).toBeNull();
    }
    expect(sanitizeCitations([base])[0].guide_url).toBeNull();
  });
});
